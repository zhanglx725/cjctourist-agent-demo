"""Offline C3 tests: one VisitorProfile drives route and TourState snapshots."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    build_agent_graph,
    direct_route_node,
    profile_collection_node,
    route_after_profile_collection,
    route_initial_request,
)
from guide_program_planner import plan_stop_program
from route_planner import plan_template
from tour_state import start_tour


def _state(text: str, initial: dict | None = None) -> dict:
    value = dict(initial or {})
    value["messages"] = [HumanMessage(content=text)]
    value["performance_metrics"] = []
    return value


class AgentProfileRouteIntegrationTests(unittest.TestCase):
    def _collected(self, text: str) -> dict:
        return profile_collection_node(_state(text))

    def test_complete_input_collects_then_starts_consistent_route_and_snapshot(self):
        collected = self._collected("我有30分钟，喜欢灰塑，标准讲解，帮我规划路线")
        self.assertEqual(route_after_profile_collection(collected), "direct_route")
        route = direct_route_node(collected)
        profile = route["visitor_profile"]
        tour = route["tour_state"]
        self.assertEqual(profile["available_minutes"], 30)
        self.assertEqual(tour["available_minutes"], profile["available_minutes"])
        self.assertEqual(tour["interests"], profile["interests"])
        self.assertEqual(tour["detail_level"], profile["detail_level"])
        self.assertEqual(route["selected_route_id"], "highlights_30")

    def test_complete_input_starts_route_in_one_deterministic_graph_turn(self):
        """C3 must join C2 collection to direct_route in the compiled graph."""
        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke(_state("选择经典模式，我有30分钟，喜欢灰塑，标准讲解，帮我规划路线"))
        self.assertEqual(result["selected_route_id"], "highlights_30")
        self.assertEqual(result["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(result["tour_state"]["available_minutes"], 30)
        self.assertEqual(result["tour_state"]["interests"], ["灰塑"])
        self.assertEqual(result["tour_state"]["detail_level"], "standard")

    def test_english_minute_route_input_starts_same_thirty_minute_route(self):
        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke(_state("选择经典模式，30min路线，木雕，详细"))
        self.assertEqual(result["selected_route_id"], "highlights_30")
        self.assertEqual(result["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(result["tour_state"]["available_minutes"], 30)
        self.assertEqual(result["tour_state"]["interests"], ["木雕"])
        self.assertEqual(result["tour_state"]["detail_level"], "deep")

    def test_minimize_walking_constraint_reaches_audited_route_selection(self):
        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke(_state(
            "选择经典模式，我有30分钟，喜欢灰塑，标准讲解，"
            "请给我规划一条少走路的路线"
        ))
        self.assertEqual(
            result["visitor_profile"]["route_constraint"], "minimize_walking"
        )
        self.assertEqual(
            result["active_route_plan"]["route_constraint"], "minimize_walking"
        )
        reason = result["active_route_plan"]["selection_reason"]
        self.assertEqual(
            reason["selected_estimated_walk_seconds"],
            min(reason["candidate_walk_seconds"].values()),
        )
        answer = result["messages"][-1].content
        self.assertIn("少走路优先", answer)
        self.assertIn("不代表现场绝对最短或无障碍路线", answer)

    def test_profile_time_drives_dynamic_route_and_plaster_interest_drives_selection(self):
        collected = self._collected("我有45分钟，喜欢灰塑，标准讲解，帮我规划路线")
        route = direct_route_node(collected)
        self.assertEqual(route["selected_route_id"], "dynamic_45")
        self.assertEqual(route["tour_state"]["available_minutes"], 45)
        program = plan_stop_program(
            "stop_front_courtyard_center", 240,
            interests=route["tour_state"]["interests"],
            detail_level=route["tour_state"]["detail_level"],
        )
        self.assertEqual(program.selected_items[0].craft, "灰塑")

    def test_detail_snapshot_controls_stop_program_item_count(self):
        counts = {}
        for detail_level in ("short", "standard", "deep"):
            tour = start_tour(plan_template("highlights_30"), interests=["灰塑"], detail_level=detail_level)
            program = plan_stop_program(
                "stop_front_courtyard_center", 300,
                interests=tour["interests"], detail_level=tour["detail_level"],
            )
            counts[detail_level] = len(program.selected_items)
        self.assertEqual(counts, {"short": 1, "standard": 2, "deep": 3})

    def test_invalid_profile_cannot_leave_partial_route_state(self):
        result = direct_route_node(_state(
            "帮我规划路线",
            {"visitor_profile": {"available_minutes": 5, "interests": [], "detail_level": "standard"}},
        ))
        self.assertNotIn("tour_state", result)
        self.assertNotIn("active_route_plan", result)
        self.assertIn("画像无效", result["messages"][0].content)

    def test_legacy_direct_route_without_profile_remains_safe(self):
        result = direct_route_node(_state("我有30分钟，帮我规划路线"))
        self.assertEqual(result["tour_state"]["available_minutes"], 30)
        self.assertEqual(result["tour_state"]["detail_level"], "standard")
        self.assertEqual(result["selected_route_id"], "highlights_30")

    def test_route_action_with_comparison_interest_enters_profile_collection(self):
        """Comparison words are route preferences when planning is explicit."""
        text = "选择经典模式，我要参观一个小时，我对三国故事相关的工艺比较感兴趣，请帮我规划路线"
        state = _state(text)
        self.assertEqual(route_initial_request(state), "profile_collection")

        collected = profile_collection_node(state)
        self.assertEqual(collected["visitor_profile"]["available_minutes"], 60)
        self.assertIn("三国", collected["visitor_profile"]["interests"])
        self.assertIn("故事", collected["visitor_profile"]["interests"])
        self.assertIn("工艺", collected["visitor_profile"]["interests"])
        self.assertIsNone(collected["profile_collection"]["next_missing_field"])
        self.assertEqual(collected["profile_collection"]["required_fields"], ["available_minutes"])

    def test_complete_route_action_with_comparison_interest_starts_sixty_minute_route(self):
        text = "选择经典模式，我要参观一个小时，我对三国故事相关的工艺比较感兴趣，标准讲解，请帮我规划路线"
        state = _state(text)
        self.assertEqual(route_initial_request(state), "profile_collection")

        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke(state)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 60)
        self.assertEqual(result["tour_state"]["available_minutes"], 60)
        self.assertIn("三国", result["tour_state"]["interests"])


if __name__ == "__main__":
    unittest.main()
