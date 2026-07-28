"""E4-3 integration tests: shared durations for profile, route, and replanning."""

from __future__ import annotations

from copy import deepcopy
import unittest

from langchain_core.messages import HumanMessage

from agent_graph import direct_route_node, route_initial_request
from profile_dialogue import collect_profile_input
from profile_update import apply_profile_update, is_profile_update_request
from tour_interaction import handle_tour_event


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class E4DurationIntegrationTests(unittest.TestCase):
    def test_chinese_hour_route_profile_and_direct_route_share_sixty_minutes(self):
        collected = collect_profile_input(
            None, "我有一个小时，喜欢灰塑，标准讲解", start_collection=True
        )
        assert collected is not None
        self.assertEqual(collected.status, "ready")
        self.assertEqual(collected.collection.profile.available_minutes, 60)

        route = direct_route_node(_state("我有一个小时，喜欢灰塑，帮我规划路线"))
        self.assertEqual(route["tour_state"]["available_minutes"], 60)
        self.assertEqual(route["visitor_profile"]["available_minutes"], 60)

    def test_half_hour_route_and_chinese_remaining_time_use_same_parser(self):
        route = direct_route_node(_state("给我规划一条半小时路线"))
        self.assertEqual(route["tour_state"]["available_minutes"], 30)
        self.assertTrue(is_profile_update_request("我现在只剩三十分钟"))

        updated = apply_profile_update(
            route["visitor_profile"], route["tour_state"], route["tour_interaction_state"],
            "我现在只剩三十分钟",
        )
        self.assertTrue(updated["ok"])
        self.assertEqual(updated["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(updated["tour_state"]["remaining_minutes"], 30)

    def test_replan_preserves_active_unconfirmed_stop_and_real_progress(self):
        route = direct_route_node(_state("我有一个小时，喜欢灰塑，帮我规划路线"))
        arrived = handle_tour_event(
            route["tour_state"], route["tour_interaction_state"], "arrive_at_stop",
            node_id="stop_front_courtyard_center",
        )
        before_visited = deepcopy(arrived["tour_state"]["visited_stop_ids"])
        before_skipped = deepcopy(arrived["tour_state"]["skipped_stop_ids"])
        updated = apply_profile_update(
            route["visitor_profile"], arrived["tour_state"], arrived["interaction_state"],
            "把时间改成一个半小时",
        )
        self.assertTrue(updated["ok"])
        self.assertEqual(updated["tour_state"]["available_minutes"], 90)
        self.assertEqual(updated["tour_state"]["current_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(updated["interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(updated["interaction_state"]["stop_phase"], "explaining")
        self.assertEqual(updated["tour_state"]["visited_stop_ids"], before_visited)
        self.assertEqual(updated["tour_state"]["skipped_stop_ids"], before_skipped)
        self.assertEqual(updated["tour_state"]["remaining_stop_ids"].count("stop_front_courtyard_center"), 1)

    def test_history_question_and_invalid_route_duration_do_not_start_a_route(self):
        self.assertEqual(route_initial_request(_state("陈家祠建了多少年？")), "direct_rag")
        collected = collect_profile_input(None, "给我规划一条一刻钟路线", start_collection=True)
        assert collected is not None
        self.assertEqual(collected.status, "clarification")
        self.assertEqual(collected.reason_code, "invalid_profile_value")


if __name__ == "__main__":
    unittest.main()
