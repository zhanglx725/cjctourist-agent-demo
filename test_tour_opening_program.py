from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import build_agent_graph, route_initial_request, tour_opening_node
from tour_opening_program import (
    apply_tour_opening_action,
    initialize_tour_opening,
    opening_action,
)


class TourOpeningProgramTests(unittest.TestCase):
    def test_opening_is_evidence_backed_replayable_and_public_safe(self):
        initial = initialize_tour_opening()
        played = apply_tour_opening_action(initial, "play")
        self.assertEqual(played["program"]["status"], "played")
        self.assertEqual(played["program"]["play_count"], 1)
        self.assertIn("陈氏书院", played["message"])
        self.assertNotIn("source_ids", played["message"])
        replayed = apply_tour_opening_action(played["program"], "replay")
        self.assertEqual(replayed["program"]["play_count"], 2)

    def test_skip_does_not_load_or_claim_narration_coverage(self):
        skipped = apply_tour_opening_action(initialize_tour_opening(), "skip")
        self.assertEqual(skipped["program"]["status"], "skipped")
        self.assertNotIn("narration_coverage", skipped)

    def test_narrow_action_parser_does_not_capture_ordinary_qa(self):
        self.assertEqual(opening_action("开始导游"), "play")
        self.assertEqual(opening_action("跳过介绍"), "skip")
        self.assertEqual(opening_action("重播开场"), "replay")
        self.assertIsNone(opening_action("陈家祠为什么又叫书院？"))

    def test_graph_route_initializes_one_pending_opening(self):
        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke({"messages": [HumanMessage(content="选择经典模式，30分钟路线")]})
        self.assertEqual(result["tour_opening_program"]["status"], "pending")
        self.assertEqual(result["tour_opening_program"]["play_count"], 0)

    def test_graph_play_skip_and_replay_only_write_opening_state(self):
        protected = {
            "tour_state": {"route_status": "not_started"},
            "visitor_profile": {"available_minutes": 30},
            "narration_coverage": {"records": []},
            "tour_opening_program": initialize_tour_opening(),
            "messages": [HumanMessage(content="开始导游")],
        }
        self.assertEqual(route_initial_request(protected), "tour_opening")
        update = tour_opening_node(protected)
        self.assertEqual(update["tour_opening_program"]["status"], "played")
        for field in ("tour_state", "visitor_profile", "narration_coverage"):
            self.assertNotIn(field, update)


if __name__ == "__main__":
    unittest.main()
