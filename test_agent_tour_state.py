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

    def test_arrival_routes_to_unified_event_node_and_adapter(self):
        initial = self._started()
        state = _message_state("我到前院中部了", initial)
        self.assertEqual(route_initial_request(state), "tour_event")
        with patch("agent_graph.handle_tour_event", wraps=agent_graph.handle_tour_event) as mocked:
            result = tour_event_node(state)
        mocked.assert_called_once()
        self.assertEqual(result["last_tour_intent"]["event_type"], "arrive_at_stop")
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "explaining")

    def test_text_confirmation_is_only_path_that_marks_visit_complete(self):
        initial = self._started()
        arrived = tour_event_node(_message_state("我到前院中部了", initial))
        completed = tour_event_node(_message_state("讲完了，去下一站", arrived))
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])
        self.assertEqual(completed["last_tour_intent"]["event_type"], "confirm_stop_complete")

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

    def test_new_route_request_keeps_direct_route_priority_after_tour_exists(self):
        initial = self._started()
        self.assertEqual(
            route_initial_request(_message_state("我有45分钟，帮我规划路线", initial)),
            "direct_route",
        )

    def test_fact_question_keeps_direct_rag_priority_after_tour_exists(self):
        initial = self._started()
        self.assertEqual(route_initial_request(_message_state("月台有什么？", initial)), "direct_rag")

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
