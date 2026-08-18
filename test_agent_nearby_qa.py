"""P4-04 Agent routing tests for nearby POI recommendations."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import route_initial_request, tour_qa_node


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class AgentNearbyQaTests(unittest.TestCase):
    def test_pending_offer_accept_and_subtype_route_to_tour_qa(self) -> None:
        initial = {
            "tour_state": {"route_status": "completed"},
            "post_visit_nearby_offer": {"status": "awaiting_choice"},
        }
        for text in ("需要", "好的", "奶茶有啥", "面食有啥", "不需要"):
            with self.subTest(text=text):
                self.assertEqual(route_initial_request(_state(text, initial)), "tour_qa")

    def test_nearby_request_routes_to_controlled_tour_qa(self) -> None:
        request = _state("陈家祠附近有什么吃饭的地方？")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("tour_qa.answer_nearby_request", return_value={"message": "周边选择", "mode": "nearby_recommendation", "nearby_pois": []}):
            update = tour_qa_node(request)
        self.assertIn("周边选择", update["messages"][0].content)
        self.assertEqual(update["retrieved_evidence"], [])

    def test_active_tour_nearby_request_is_read_only(self) -> None:
        initial = {
            "tour_state": {"route_status": "touring", "current_stop_id": "label_moon_platform", "remaining_stop_ids": ["stop_front_courtyard_center"]},
            "tour_interaction_state": {"stop_phase": "explaining"},
            "visitor_profile": {"interests": ["灰塑"]},
        }
        before = deepcopy(initial)
        request = _state("参观完想去附近喝咖啡", initial)
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        self.assertNotIn("visitor_profile", update)
        self.assertEqual(initial, before)
        self.assertNotIn("未改变陈家祠馆内路线", update["messages"][0].content)

    def test_indoor_milk_tea_question_remains_a_safety_question(self) -> None:
        request = _state("展厅里面能喝奶茶吗？")
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        self.assertIn("不能带入展厅", update["messages"][0].content)
        self.assertNotIn("已审核周边候选", update["messages"][0].content)

    def test_onboarding_nearby_request_answers_then_resumes(self) -> None:
        request = _state("附近哪里可以买手信", {"visitor_welcome_program": {"status": "awaiting_language"}})
        self.assertEqual(route_initial_request(request), "tour_qa")

    def test_route_mutation_request_gets_boundary_clarification(self) -> None:
        request = _state("把附近的奶茶店加入我的游览路线。")
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        self.assertIn("不会把周边地点加入陈家祠游览路线", update["messages"][0].content)
        self.assertNotIn("tour_state", update)


if __name__ == "__main__":
    unittest.main()
