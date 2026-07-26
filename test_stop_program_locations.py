"""Offline B3.1 location-hint tests for audited point mappings."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from guide_narration import compose_guide_narration
from guide_program_planner import plan_stop_program


def _card(ornament: dict[str, str]) -> dict[str, dict[str, object]]:
    return {
        "test_stop": {
            "node_id": "test_stop",
            "display_name": "测试庭院",
            "ornaments": [ornament],
            "rag_queries": [f"{ornament['name']} 是什么装饰"],
        }
    }


class StopProgramLocationTests(unittest.TestCase):
    def setUp(self):
        self.reviewed_item = {
            "ornament_id": "orn_location_001",
            "name": "测试灰塑",
            "craft": "灰塑",
            "raw_location": "建筑山墙垂脊前沿",
            "final_node_id": "test_stop",
            "mapping_decision": "change",
            "mapping_source": "manual_review_existing_node",
        }

    def test_reviewed_explicit_location_enters_program_and_narration(self):
        with patch("guide_program_planner.load_guide_cards", return_value=_card(self.reviewed_item)):
            program = plan_stop_program("test_stop", 120, detail_level="short")
        item = program.selected_items[0]
        self.assertEqual(item.raw_location, "建筑山墙垂脊前沿")
        self.assertEqual(item.observation_location, "建筑山墙垂脊前沿")
        self.assertEqual(item.location_source, "ornament_spatial_mapping_v1")
        narration = compose_guide_narration(
            program,
            {item.ornament_id: [{"source_ids": ["S10"], "content": "灰塑是岭南建筑常见的装饰艺术。"}]},
        )
        self.assertIn("在建筑山墙垂脊前沿，这是一处灰塑装饰", narration.visitor_message)
        self.assertNotIn("ornament_spatial_mapping_v1", narration.visitor_message)
        self.assertNotIn("raw_location", narration.visitor_message)

    def test_mismatched_node_or_unreviewed_mapping_cannot_supply_hint(self):
        mismatched = deepcopy(self.reviewed_item)
        mismatched["final_node_id"] = "other_stop"
        unreviewed = deepcopy(self.reviewed_item)
        unreviewed["mapping_decision"] = "draft"
        for candidate in (mismatched, unreviewed):
            with self.subTest(candidate=candidate):
                with patch("guide_program_planner.load_guide_cards", return_value=_card(candidate)):
                    program = plan_stop_program("test_stop", 120, detail_level="short")
                item = program.selected_items[0]
                self.assertIsNone(item.raw_location)
                self.assertIsNone(item.observation_location)
                self.assertIsNone(item.location_source)

    def test_empty_or_coarse_location_safely_uses_generic_prompt(self):
        for raw_location in ("", "测试庭院"):
            candidate = deepcopy(self.reviewed_item)
            candidate["raw_location"] = raw_location
            with self.subTest(raw_location=raw_location):
                with patch("guide_program_planner.load_guide_cards", return_value=_card(candidate)):
                    program = plan_stop_program("test_stop", 120, detail_level="short")
                item = program.selected_items[0]
                self.assertIsNone(item.observation_location)
                narration = compose_guide_narration(program, {item.ornament_id: []})
                self.assertNotIn("请先看向", narration.visitor_message)

    def test_location_metadata_does_not_change_budget_or_program_determinism(self):
        with patch("guide_program_planner.load_guide_cards", return_value=_card(self.reviewed_item)):
            first = plan_stop_program("test_stop", 120, detail_level="short")
            second = plan_stop_program("test_stop", 120, detail_level="short")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.allocated_content_seconds, 90)
        self.assertLessEqual(first.allocated_content_seconds, first.budget_seconds)


if __name__ == "__main__":
    unittest.main()
