"""No-network integration tests for A1-2 Agent routing and A1-1 state safety."""

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import direct_route_node, route_initial_request, tour_event_node


def _message_state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class AgentTourStateTests(unittest.TestCase):
    def _started(self) -> dict:
        return direct_route_node(_message_state("我有30分钟，帮我规划路线"))

    def test_start_route_initializes_session_tour_and_interaction_state(self):
        result = self._started()
        self.assertEqual(result["tour_state"]["selected_route_id"], "highlights_30")
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "navigating")
        self.assertIn("arrive_at_stop", [item["id"] for item in result["tour_presentation"]["actions"]])

    def test_arrival_routes_to_unified_event_node_and_adapter(self):
        initial = self._started()
        state = _message_state("我到了", initial)
        self.assertEqual(route_initial_request(state), "tour_event")
        with patch("agent_graph.handle_tour_event", wraps=agent_graph.handle_tour_event) as mocked:
            result = tour_event_node(state)
        mocked.assert_called_once()
        self.assertEqual(result["last_tour_intent"]["event_type"], "arrive_at_stop")
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "explaining")
        self.assertEqual(result["tour_presentation"]["phase"], "explaining")
        self.assertIn("explanation_finished", [item["id"] for item in result["tour_presentation"]["actions"]])

    def test_generic_arrival_uses_pending_stop_only_through_adapter(self):
        initial = self._started()
        state = _message_state("我到了", initial)
        self.assertEqual(route_initial_request(state), "tour_event")
        with patch("agent_graph.handle_tour_event", wraps=agent_graph.handle_tour_event) as mocked:
            result = tour_event_node(state)
        mocked.assert_called_once_with(
            initial["tour_state"], initial["tour_interaction_state"], "arrive_at_stop",
            node_id=initial["tour_interaction_state"]["pending_stop_id"],
        )
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "explaining")

    def test_text_confirmation_is_only_path_that_marks_visit_complete(self):
        initial = self._started()
        pending = initial["tour_interaction_state"]["pending_stop_id"]
        arrived = tour_event_node(_message_state("我到了", initial))
        completed = tour_event_node(_message_state("讲完了，去下一站", arrived))
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], [pending])
        self.assertEqual(completed["last_tour_intent"]["event_type"], "confirm_stop_complete")

    def test_explicit_confirmation_text_marks_visit_complete_only_after_arrival(self):
        initial = self._started()
        pending = initial["tour_interaction_state"]["pending_stop_id"]
        arrived = tour_event_node(_message_state("我到了", initial))
        completed = tour_event_node(_message_state("确认完成本点", arrived))
        self.assertEqual(completed["last_tour_intent"]["event_type"], "confirm_stop_complete")
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], [pending])
        self.assertEqual(completed["tour_interaction_state"]["stop_phase"], "navigating")

    def test_completion_synonyms_use_adapter_and_preserve_a1_lifecycle(self):
        for completion_text, finish_explanation in (
            ("完成本点", False),
            ("本点完成", True),
            ("可以去下一站了", True),
            ("完成", False),
        ):
            with self.subTest(completion_text=completion_text, finish_explanation=finish_explanation):
                initial = self._started()
                pending = initial["tour_interaction_state"]["pending_stop_id"]
                arrived = tour_event_node(_message_state("我到了", initial))
                state = arrived
                if finish_explanation:
                    state = tour_event_node(_message_state("本点讲解结束", arrived))
                    self.assertEqual(state["tour_interaction_state"]["stop_phase"], "awaiting_confirmation")
                request = _message_state(completion_text, state)
                self.assertEqual(route_initial_request(request), "tour_event")
                completed = tour_event_node(request)
                self.assertEqual(completed["last_tour_intent"]["event_type"], "confirm_stop_complete")
                self.assertEqual(completed["tour_state"]["visited_stop_ids"], [pending])
                self.assertNotIn(pending, completed["tour_state"]["remaining_stop_ids"])
                self.assertEqual(completed["tour_interaction_state"]["stop_phase"], "navigating")

    def test_completion_controls_reject_without_llm_or_rag_and_keep_state(self):
        initial = self._started()
        before_tour = initial["tour_state"]
        before_interaction = initial["tour_interaction_state"]
        for text in (
            "完成本点", "还没完成本点", "不要完成本点", "完成本点是什么意思？", "完成",
        ):
            with self.subTest(text=text):
                request = _message_state(text, initial)
                route = route_initial_request(request)
                self.assertNotIn(route, {"llm_think", "rag_tool", "tour_qa"})
                if route == "tour_event":
                    result = tour_event_node(request)
                    self.assertFalse(result["last_tour_event"]["ok"])
                    self.assertEqual(result["tour_state"], before_tour)
                    self.assertEqual(result["tour_interaction_state"], before_interaction)
                else:
                    self.assertEqual(route, "clarification")
                self.assertEqual(initial["tour_state"], before_tour)
                self.assertEqual(initial["tour_interaction_state"], before_interaction)

    def test_self_arrival_and_pending_replan_do_not_treat_completion_as_replan_confirmation(self):
        initial = self._started()
        self_arrived = tour_event_node(_message_state("我到月台了", initial))
        request = _message_state("完成本点", self_arrived)
        route = route_initial_request(request)
        self.assertNotIn(route, {"llm_think", "rag_tool", "tour_qa"})
        self.assertNotEqual(route, "confirm_replan")
        self.assertEqual(self_arrived["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(self_arrived["tour_interaction_state"]["pending_stop_id"], initial["tour_interaction_state"]["pending_stop_id"])

    def test_repeated_or_finished_text_completion_is_idempotent_or_rejected_without_fallback(self):
        initial = self._started()
        arrived = tour_event_node(_message_state("我到了", initial))
        completed = tour_event_node(_message_state("完成本点", arrived))
        replay_request = _message_state("完成本点", completed)
        self.assertEqual(route_initial_request(replay_request), "tour_event")
        replay = tour_event_node(replay_request)
        self.assertEqual(replay["tour_state"], completed["tour_state"])
        self.assertEqual(replay["tour_interaction_state"], completed["tour_interaction_state"])
        self.assertEqual(replay["tour_state"]["visited_stop_ids"], completed["tour_state"]["visited_stop_ids"])

        finished = tour_event_node(_message_state("结束导览", initial))
        finished_request = _message_state("完成本点", finished)
        route = route_initial_request(finished_request)
        self.assertEqual(route, "tour_event")
        self.assertNotIn(route, {"llm_think", "rag_tool", "tour_qa"})
        rejected = tour_event_node(finished_request)
        self.assertFalse(rejected["last_tour_event"]["ok"])
        self.assertEqual(rejected["tour_state"], finished["tour_state"])
        self.assertEqual(rejected["tour_interaction_state"], finished["tour_interaction_state"])

    def test_text_explanation_end_only_enters_awaiting_confirmation(self):
        initial = self._started()
        pending = initial["tour_interaction_state"]["pending_stop_id"]
        arrived = tour_event_node(_message_state("我到了", initial))
        request = _message_state("本点讲解结束", arrived)
        self.assertEqual(route_initial_request(request), "tour_event")
        result = tour_event_node(request)
        self.assertEqual(result["last_tour_intent"]["event_type"], "explanation_finished")
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_interaction_state"]["pending_stop_id"], pending)
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "awaiting_confirmation")

    def test_text_explanation_end_before_arrival_is_rejected_by_adapter(self):
        initial = self._started()
        request = _message_state("讲解播放结束了", initial)
        self.assertEqual(route_initial_request(request), "tour_event")
        result = tour_event_node(request)
        self.assertEqual(result["last_tour_intent"]["event_type"], "explanation_finished")
        self.assertFalse(result["last_tour_event"]["ok"])
        self.assertEqual(result["tour_state"], initial["tour_state"])
        self.assertEqual(result["tour_interaction_state"], initial["tour_interaction_state"])

    def test_next_stop_how_to_walk_is_read_only_navigation(self):
        initial = self._started()
        request = _message_state("下一站怎么走", initial)
        self.assertEqual(route_initial_request(request), "tour_event")
        result = tour_event_node(request)
        self.assertEqual(result["last_tour_intent"]["event_type"], "next_stop")
        self.assertEqual(result["tour_state"], initial["tour_state"])
        self.assertEqual(result["tour_interaction_state"], initial["tour_interaction_state"])

    def test_multi_intent_returns_clarification_without_state_change(self):
        initial = self._started()
        state = _message_state("我到月台了，顺便讲讲月台石雕", initial)
        self.assertEqual(route_initial_request(state), "clarification")
        before = initial["tour_state"]
        from agent_graph import clarification_node
        result = clarification_node(state)
        self.assertEqual(result["last_tour_intent"]["reason_code"], "multiple_intents")
        self.assertNotIn("tour_state", result)
        self.assertEqual(before["visited_stop_ids"], [])

    def test_new_route_request_collects_profile_before_later_route_replacement(self):
        initial = self._started()
        self.assertEqual(
            route_initial_request(_message_state("我有45分钟，帮我规划路线", initial)),
            "profile_collection",
        )

    def test_point_inventory_question_uses_tour_qa_after_tour_exists(self):
        initial = self._started()
        self.assertEqual(route_initial_request(_message_state("月台有什么？", initial)), "tour_qa")

    def test_static_location_context_routes_to_qa_not_arrival(self):
        initial = self._started()
        self.assertEqual(
            route_initial_request(_message_state("我在月台能看到什么？", initial)),
            "tour_qa",
        )

    def test_open_conversation_keeps_llm_path(self):
        self.assertEqual(route_initial_request(_message_state("你好")), "llm_think")

    def test_uninitialized_control_goes_to_adapter_and_does_not_create_state(self):
        state = _message_state("下一站去哪？")
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertEqual(result["last_tour_intent"]["event_type"], "next_stop")
        self.assertNotIn("tour_state", result)
        self.assertIn("先建立游览路线", result["messages"][0].content)

    def test_finished_tour_event_is_rejected_without_state_mutation(self):
        initial = self._started()
        finished = tour_event_node(_message_state("结束导览", initial))
        rejected = tour_event_node(_message_state("下一站去哪？", finished))
        self.assertEqual(rejected["last_tour_intent"]["event_type"], "next_stop")
        self.assertEqual(rejected["tour_state"], finished["tour_state"])
        self.assertIn("已经结束", rejected["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
