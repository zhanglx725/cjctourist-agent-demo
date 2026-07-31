"""Agent-level P1-11 routing without model or RAG calls."""

import unittest
from copy import deepcopy

from langchain_core.messages import HumanMessage

from agent_graph import (
    cancel_replan_node,
    confirm_replan_node,
    prepare_replan_node,
    prepare_replan_candidate_node,
    route_initial_request,
    route_after_confirm_replan,
    show_replan_node,
    show_replan_time_node,
    tour_event_node,
)
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


class AgentExplicitLocationReplanTests(unittest.TestCase):
    def _active_state(self):
        tour = start_tour(plan_template("crafts_60"), interests=["灰塑", "木雕"])
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        completed = handle_tour_event(arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete")
        return {
            "messages": [HumanMessage(content="我已经到后庭西侧了，在这个点重新安排后续行程。")],
            "tour_state": completed["tour_state"],
            "tour_interaction_state": completed["interaction_state"],
            "visitor_profile": {"available_minutes": 60, "interests": ["灰塑", "木雕"], "detail_level": "standard"},
            "performance_metrics": [],
        }

    def _pending_route_confirmation_state(self):
        """Create a real two-stage P1-11 proposal ready for confirmation."""
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后庭了")]
        time_confirmation = tour_event_node(state)
        candidate_state = {
            **state,
            **time_confirmation,
            "messages": [HumanMessage(content="我还有30分钟")],
        }
        candidate = prepare_replan_candidate_node(candidate_state)
        return {**candidate_state, **candidate}

    def test_agent_requests_time_then_previews_and_confirms_from_explicit_location(self):
        state = self._active_state()
        old_pending = state["tour_interaction_state"]["pending_stop_id"]
        old_route = state["tour_state"].copy()
        self.assertEqual(route_initial_request(state), "prepare_replan")
        preview = prepare_replan_node(state)
        self.assertEqual(preview["tour_state"]["current_stop_id"], "stop_rear_courtyard_west")
        self.assertEqual(preview["pending_replan_time_confirmation"]["origin_node_id"], "stop_rear_courtyard_west")
        self.assertIsNone(preview["pending_replan_proposal"])
        self.assertEqual(preview["tour_state"]["visited_stop_ids"], old_route["visited_stop_ids"])
        self.assertEqual(preview["tour_interaction_state"]["pending_stop_id"], old_pending)
        self.assertEqual(preview["tour_presentation"]["phase"], "replan_time_confirmation")
        self.assertIn("还剩多少时间", preview["tour_presentation"]["message"])
        time_state = {**state, **preview, "messages": [HumanMessage(content="我还有30分钟")]}
        self.assertEqual(route_initial_request(time_state), "prepare_replan_candidate")
        candidate = prepare_replan_candidate_node(time_state)
        self.assertEqual(candidate["pending_replan_proposal"]["origin_node_id"], "stop_rear_courtyard_west")
        self.assertEqual(candidate["pending_replan_proposal"]["remaining_minutes"], 30)
        self.assertEqual(candidate["tour_presentation"]["phase"], "replan_route_confirmation")
        confirm_state = {**time_state, **candidate, "messages": [HumanMessage(content="确认使用这条后续路线。")]}
        self.assertEqual(route_initial_request(confirm_state), "confirm_replan")
        applied = confirm_replan_node(confirm_state)
        self.assertIsNone(applied["pending_replan_proposal"])
        self.assertEqual(applied["tour_state"]["current_stop_id"], "stop_rear_courtyard_west")
        self.assertIn("stop_front_courtyard_center", applied["tour_state"]["visited_stop_ids"])
        self.assertIn(applied["tour_interaction_state"]["pending_stop_id"], applied["tour_state"]["remaining_stop_ids"])

    def test_unrelated_knowledge_question_does_not_prepare_replan(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="后庭西侧有什么？")]
        self.assertNotEqual(route_initial_request(state), "prepare_replan")

    def test_non_pending_arrival_automatically_requests_remaining_time(self):
        state = self._active_state()
        old_route = state["tour_state"].copy()
        old_pending = state["tour_interaction_state"]["pending_stop_id"]
        state["messages"] = [HumanMessage(content="我到后庭了")]
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertEqual(result["tour_state"]["current_stop_id"], "stop_rear_courtyard")
        self.assertEqual(result["tour_state"].get("last_arrival_kind"), "self_arrival")
        self.assertEqual(result["pending_replan_time_confirmation"]["origin_node_id"], "stop_rear_courtyard")
        self.assertIsNone(result["pending_replan_proposal"])
        self.assertEqual(result["tour_interaction_state"]["pending_stop_id"], old_pending)
        self.assertEqual(result["tour_state"]["visited_stop_ids"], old_route["visited_stop_ids"])
        self.assertEqual(result["tour_presentation"]["phase"], "replan_time_confirmation")
        self.assertIn("还剩多少时间", result["tour_presentation"]["message"])

    def test_pending_arrival_keeps_normal_stop_guidance_path(self):
        state = self._active_state()
        pending = state["tour_interaction_state"]["pending_stop_id"]
        from route_planner import _read_catalog
        state["messages"] = [HumanMessage(content=f"我到{_read_catalog()[pending]['stop_name']}了")]
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertEqual(result["last_tour_event"]["code"], "arrived")
        self.assertIsNone(result.get("pending_replan_proposal"))

    def test_self_arrival_time_confirmation_proves_rear_east_origin_then_short_confirmation(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后东庭了")]
        self.assertEqual(route_initial_request(state), "tour_event")
        preview = tour_event_node(state)
        confirmation = preview["pending_replan_time_confirmation"]
        self.assertEqual(preview["tour_state"]["current_stop_id"], "stop_rear_east_courtyard_inner")
        self.assertEqual(confirmation["origin_node_id"], "stop_rear_east_courtyard_inner")
        self.assertEqual(confirmation["physical_node_snapshot"], confirmation["origin_node_id"])
        self.assertIn("还剩多少时间", preview["tour_presentation"]["message"])

        time_state = {**state, **preview, "messages": [HumanMessage(content="我还有30分钟")]}
        candidate = prepare_replan_candidate_node(time_state)
        proposal = candidate["pending_replan_proposal"]
        self.assertEqual(proposal["path_node_ids"][0], proposal["origin_node_id"])
        self.assertEqual(proposal["route_segments"][0]["from_node_id"], proposal["origin_node_id"])
        self.assertIn("已从后东庭出发", candidate["tour_presentation"]["message"])
        self.assertIn("路线起点：后东庭", candidate["tour_presentation"]["message"])
        confirm_state = {**time_state, **candidate, "messages": [HumanMessage(content="确认")]}
        self.assertEqual(route_initial_request(confirm_state), "confirm_replan")
        applied = confirm_replan_node(confirm_state)
        self.assertIsNone(applied["pending_replan_proposal"])
        self.assertEqual(applied["tour_state"]["current_stop_id"], "stop_rear_east_courtyard_inner")

    def test_pending_proposal_short_cancel_and_repeat_are_contextual(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后东庭了")]
        preview = tour_event_node(state)
        pending_state = {**state, **preview}
        pending_state["messages"] = [HumanMessage(content="路线有哪些点？")]
        self.assertEqual(route_initial_request(pending_state), "show_replan_time")
        self.assertIsNotNone(preview["pending_replan_time_confirmation"])
        pending_state["messages"] = [HumanMessage(content="继续原路线")]
        self.assertEqual(route_initial_request(pending_state), "cancel_replan")
        cancelled = cancel_replan_node(pending_state)
        self.assertIsNone(cancelled["pending_replan_proposal"])
        self.assertEqual(cancelled.get("tour_state"), None)

    def test_bare_confirmation_keeps_a1_completion_when_no_replan_is_pending(self):
        state = self._active_state()
        pending = state["tour_interaction_state"]["pending_stop_id"]
        arrived = handle_tour_event(
            state["tour_state"], state["tour_interaction_state"], "arrive_at_stop", node_id=pending
        )
        explained = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "explanation_finished"
        )
        state.update({
            "tour_state": explained["tour_state"],
            "tour_interaction_state": explained["interaction_state"],
            "messages": [HumanMessage(content="确认")],
        })
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertEqual(result["last_tour_event"]["code"], "stop_completed")

    def test_new_arrival_replaces_a_stale_pending_time_confirmation(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后东庭了")]
        first = tour_event_node(state)
        replacement_state = {**state, **first, "messages": [HumanMessage(content="我到后庭了")]}
        self.assertEqual(route_initial_request(replacement_state), "tour_event")
        replacement = tour_event_node(replacement_state)
        self.assertEqual(replacement["pending_replan_time_confirmation"]["origin_node_id"], "stop_rear_courtyard")

    def test_next_stop_is_blocked_in_both_replan_confirmation_phases(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后庭了")]
        time_confirmation = tour_event_node(state)
        pending_time_state = {**state, **time_confirmation, "messages": [HumanMessage(content="下一站")]}
        self.assertEqual(route_initial_request(pending_time_state), "show_replan_time")
        self.assertEqual(pending_time_state["tour_state"]["route_status"], "touring")
        self.assertEqual(pending_time_state["tour_state"]["visited_stop_ids"], state["tour_state"]["visited_stop_ids"])

        candidate_state = {**state, **time_confirmation, "messages": [HumanMessage(content="我还有30分钟")]}
        candidate = prepare_replan_candidate_node(candidate_state)
        pending_route_state = {**candidate_state, **candidate, "messages": [HumanMessage(content="下一站")]}
        self.assertEqual(route_initial_request(pending_route_state), "show_replan")
        self.assertEqual(pending_route_state["tour_state"]["route_status"], "touring")

    def test_time_confirmation_bare_confirm_does_not_create_a_candidate(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后庭了")]
        preview = tour_event_node(state)
        confirm_state = {**state, **preview, "messages": [HumanMessage(content="确认")]}
        self.assertEqual(route_initial_request(confirm_state), "show_replan_time")
        self.assertIsNone(confirm_state["pending_replan_proposal"])

    def test_time_confirmation_reuses_supported_duration_parser_forms(self):
        for text, expected_minutes in (
            ("我还有30分钟", 30),
            ("还有半小时", 30),
            ("还有一个小时", 60),
            ("还有1.5小时", 90),
            ("按30分钟安排", 30),
        ):
            with self.subTest(text=text):
                state = self._active_state()
                state["messages"] = [HumanMessage(content="我到后庭了")]
                time_confirmation = tour_event_node(state)
                candidate_state = {**state, **time_confirmation, "messages": [HumanMessage(content=text)]}
                self.assertEqual(route_initial_request(candidate_state), "prepare_replan_candidate")
                candidate = prepare_replan_candidate_node(candidate_state)
                self.assertEqual(candidate["pending_replan_proposal"]["remaining_minutes"], expected_minutes)
                self.assertIsNone(candidate["pending_replan_time_confirmation"])
                self.assertEqual(candidate["tour_state"], time_confirmation["tour_state"])

    def test_time_confirmation_cancel_keeps_real_position_and_formal_route(self):
        state = self._active_state()
        formal_before = state["tour_state"]
        state["messages"] = [HumanMessage(content="我到后庭了")]
        confirmation = tour_event_node(state)
        cancelled = cancel_replan_node({**state, **confirmation})
        self.assertIsNone(cancelled["pending_replan_time_confirmation"])
        self.assertIsNone(cancelled["pending_replan_proposal"])
        self.assertEqual(cancelled["tour_interaction_state"]["pending_action_kind"], None)
        self.assertEqual(confirmation["tour_state"]["current_stop_id"], "stop_rear_courtyard")
        self.assertEqual(confirmation["tour_state"]["remaining_stop_ids"], formal_before["remaining_stop_ids"])
        self.assertEqual(confirmation["tour_state"]["visited_stop_ids"], formal_before["visited_stop_ids"])

    def test_confirmed_candidate_never_finishes_route_before_navigation_or_guidance(self):
        state = self._active_state()
        state["messages"] = [HumanMessage(content="我到后庭了")]
        time_confirmation = tour_event_node(state)
        candidate_state = {**state, **time_confirmation, "messages": [HumanMessage(content="我还有30分钟")]}
        candidate = prepare_replan_candidate_node(candidate_state)
        applied = confirm_replan_node({**candidate_state, **candidate, "messages": [HumanMessage(content="确认")]})
        applied_state = {**candidate_state, **candidate, **applied}
        self.assertEqual(applied["tour_state"]["route_status"], "touring")
        self.assertIsNone(applied["pending_replan_proposal"])
        self.assertEqual(route_after_confirm_replan(applied_state), "stop_guidance")
        self.assertNotEqual(applied["last_tour_event"]["code"], "tour_finished")

    def test_pending_route_confirmation_accepts_normalized_confirm_expressions(self):
        expressions = (
            "确认",
            "确认新路线",
            "确认使用新路线",
            "确认这条路线",
            "使用新路线",
            "使用这条路线",
            "采用新路线",
            "就用新路线",
            "就按新路线走",
            "按这条路线走",
            "按这个规划走",
            "用这个方案",
            "可以，就这样走",
            "好的，使用新路线",
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                candidate_state = self._pending_route_confirmation_state()
                before_tour = deepcopy(candidate_state["tour_state"])
                before_interaction = deepcopy(candidate_state["tour_interaction_state"])
                confirm_state = {
                    **candidate_state,
                    "messages": [HumanMessage(content=f"  {expression}。  ")],
                }
                self.assertEqual(route_initial_request(confirm_state), "confirm_replan")
                applied = confirm_replan_node(confirm_state)
                self.assertTrue(applied["last_tour_event"]["ok"])
                self.assertIsNone(applied["pending_replan_proposal"])
                self.assertEqual(applied["tour_state"]["current_stop_id"], before_tour["current_stop_id"])
                self.assertEqual(applied["tour_state"]["visited_stop_ids"], before_tour["visited_stop_ids"])
                self.assertEqual(applied["tour_state"]["skipped_stop_ids"], before_tour["skipped_stop_ids"])
                self.assertEqual(applied["tour_interaction_state"]["pending_action_kind"], None)
                self.assertEqual(
                    applied["active_route_plan"]["route_id"],
                    candidate_state["pending_replan_proposal"]["route_id"],
                )
                self.assertEqual(before_interaction["pending_action_kind"], "replan_route_confirmation")
                repeated_state = {
                    **confirm_state,
                    **applied,
                    "messages": [HumanMessage(content=expression)],
                }
                self.assertNotEqual(route_initial_request(repeated_state), "confirm_replan")

    def test_pending_route_confirmation_negatives_and_questions_do_not_apply(self):
        negative_expressions = (
            "不确认新路线",
            "不要使用新路线",
            "继续原路线",
            "我没说确认",
        )
        for expression in negative_expressions:
            with self.subTest(expression=expression):
                candidate_state = self._pending_route_confirmation_state()
                control_state = {**candidate_state, "messages": [HumanMessage(content=expression)]}
                self.assertEqual(route_initial_request(control_state), "cancel_replan")
                cancelled = cancel_replan_node(control_state)
                self.assertIsNone(cancelled["pending_replan_proposal"])
                self.assertIsNone(cancelled["pending_replan_time_confirmation"])
                self.assertEqual(cancelled["tour_interaction_state"]["pending_action_kind"], None)
                self.assertNotIn("tour_state", cancelled)

        view_expressions = (
            "确认新路线是什么意思？",
            "确认后有哪些点？",
            "我可以确认吗？",
            "再说一下新路线",
        )
        for expression in view_expressions:
            with self.subTest(expression=expression):
                candidate_state = self._pending_route_confirmation_state()
                control_state = {**candidate_state, "messages": [HumanMessage(content=expression)]}
                self.assertEqual(route_initial_request(control_state), "show_replan")
                shown = show_replan_node(control_state)
                self.assertEqual(shown["pending_replan_proposal"], candidate_state["pending_replan_proposal"])
                self.assertNotIn("tour_state", shown)

    def test_route_confirmation_requires_fresh_proposal_and_correct_phase(self):
        candidate_state = self._pending_route_confirmation_state()
        time_stage = self._active_state()
        time_stage["messages"] = [HumanMessage(content="我到后庭了")]
        time_confirmation = tour_event_node(time_stage)
        waiting_for_time = {
            **time_stage,
            **time_confirmation,
            "messages": [HumanMessage(content="确认新路线")],
        }
        self.assertEqual(route_initial_request(waiting_for_time), "show_replan_time")
        self.assertEqual(show_replan_time_node(waiting_for_time)["tour_presentation"]["phase"], "replan_time_confirmation")

        no_proposal = self._active_state()
        no_proposal["messages"] = [HumanMessage(content="确认新路线")]
        self.assertNotEqual(route_initial_request(no_proposal), "confirm_replan")

        moved = handle_tour_event(
            candidate_state["tour_state"],
            candidate_state["tour_interaction_state"],
            "arrive_at_stop",
            node_id="label_moon_platform",
        )
        stale = {
            **candidate_state,
            "tour_state": moved["tour_state"],
            "tour_interaction_state": moved["interaction_state"],
            "messages": [HumanMessage(content="确认新路线")],
        }
        self.assertEqual(route_initial_request(stale), "show_replan")


if __name__ == "__main__":
    unittest.main()
