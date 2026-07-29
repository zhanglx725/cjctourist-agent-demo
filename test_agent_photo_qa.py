"""Offline Agent routing tests for D6 photo recommendations."""

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


class AgentPhotoQaTests(unittest.TestCase):
    def test_photo_request_routes_to_tour_qa_without_rag(self) -> None:
        request = _state("给我推荐几个打卡点")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("tour_qa.answer_photo_request", return_value={"message": "项目编辑建议", "mode": "photo_recommendation", "photo_spots": [], "point_context": None}):
            update = tour_qa_node(request)
        self.assertIn("项目编辑建议", update["messages"][0].content)
        self.assertEqual(update["retrieved_evidence"], [])

    def test_photo_route_change_clarifies_without_state_change(self) -> None:
        initial = {"tour_state": {"visited_stop_ids": ["label_moon_platform"], "remaining_stop_ids": ["stop_front_courtyard_center"], "route_status": "touring"}, "tour_interaction_state": {"stop_phase": "explaining"}}
        request = _state("把这个打卡点加入路线", initial)
        before = deepcopy(initial)
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        self.assertEqual(initial, before)
        self.assertIn("不会自动把打卡点加入路线", update["messages"][0].content)

    def test_drone_request_routes_to_safety_before_photo_candidates(self) -> None:
        initial = {
            "tour_state": {
                "current_stop_id": "label_moon_platform",
                "route_status": "touring",
            },
            "tour_interaction_state": {"stop_phase": "explaining"},
        }
        request = _state("我想带无人机去拍陈家祠，可以直接飞吗？", initial)
        before = deepcopy(initial)
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        answer = update["messages"][0].content
        self.assertIn("不可以直接使用无人机航拍", answer)
        self.assertIn("全域禁飞", answer)
        self.assertNotIn("打卡候选", answer)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        self.assertEqual(initial, before)

    def test_non_photo_safety_question_uses_the_same_controlled_answer(self) -> None:
        request = _state("陈家祠庭院里可以抽烟吗？")
        self.assertEqual(route_initial_request(request), "tour_qa")
        update = tour_qa_node(request)
        self.assertIn("不可以在陈家祠内吸烟", update["messages"][0].content)
        self.assertEqual(update["retrieved_evidence"], [])

    def test_arrival_and_d2_d3_d4_requests_keep_existing_routes(self) -> None:
        active = {"tour_state": {"current_stop_id": "label_moon_platform", "route_status": "touring"}, "tour_interaction_state": {"pending_stop_id": "label_moon_platform", "stop_phase": "navigating"}}
        self.assertEqual(route_initial_request(_state("我到月台了", active)), "tour_event")
        self.assertEqual(route_initial_request(_state("灰塑是什么？", active)), "tour_qa")
        self.assertEqual(route_initial_request(_state("从研究角度如何理解灰塑？", active)), "tour_qa")
        self.assertEqual(route_initial_request(_state("灰塑和砖雕有什么区别？", active)), "tour_qa")


if __name__ == "__main__":
    unittest.main()
