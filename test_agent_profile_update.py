"""Offline C4 Agent routing tests; no model or network call is allowed."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import direct_route_node, profile_update_node, route_initial_request


def _state(text: str, initial: dict | None = None) -> dict:
    result = dict(initial or {})
    result["messages"] = [HumanMessage(content=text)]
    result["performance_metrics"] = []
    return result


class AgentProfileUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = direct_route_node(_state("我有30分钟，喜欢灰塑，标准讲解，帮我规划路线"))

    def test_time_update_uses_controlled_profile_node_not_plain_event_node(self):
        state = _state("我只剩20分钟", self.initial)
        self.assertEqual(route_initial_request(state), "profile_update")
        result = profile_update_node(state)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 20)
        self.assertEqual(result["tour_state"]["available_minutes"], 20)
        self.assertEqual(result["tour_state"]["remaining_minutes"], 20)

    def test_interest_and_detail_updates_preserve_route_and_change_snapshot(self):
        interest = profile_update_node(_state("接下来想多看木雕", self.initial))
        self.assertEqual(interest["tour_state"]["interests"], ["木雕"])
        self.assertEqual(interest["tour_state"]["route_stop_ids"], self.initial["tour_state"]["route_stop_ids"])
        detail = profile_update_node(_state("我想听深入一点", interest))
        self.assertEqual(detail["tour_state"]["detail_level"], "deep")
        self.assertEqual(detail["tour_state"]["visited_stop_ids"], [])

    def test_control_and_preference_in_one_turn_has_no_partial_update(self):
        state = _state("我到前院中部了，后面简单讲", self.initial)
        self.assertEqual(route_initial_request(state), "profile_update")
        result = profile_update_node(state)
        self.assertNotIn("tour_state", result)
        self.assertEqual(result["last_profile_update"]["code"], "multiple_intents")
        self.assertEqual(self.initial["tour_state"]["detail_level"], "standard")

    def test_current_point_question_remains_tour_qa_not_profile_update(self):
        self.assertEqual(route_initial_request(_state("这里的灰塑有什么特点？", self.initial)), "tour_qa")


if __name__ == "__main__":
    unittest.main()
