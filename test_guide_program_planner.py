"""Offline B1 tests for deterministic, reviewed-ornament StopPrograms."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from guide_program_planner import GuideProgramError, plan_stop_program
from tour_qa import load_guide_cards


class GuideProgramPlannerTests(unittest.TestCase):
    def test_selected_items_only_come_from_the_reviewed_current_point_card(self):
        cards = load_guide_cards()
        program = plan_stop_program("label_moon_platform", 300, detail_level="deep")
        approved_ids = {item["ornament_id"] for item in cards["label_moon_platform"]["ornaments"]}
        self.assertGreaterEqual(len(program.selected_items), 1)
        self.assertLessEqual(len(program.selected_items), 3)
        self.assertTrue({item.ornament_id for item in program.selected_items}.issubset(approved_ids))
        self.assertLessEqual(sum(item.planned_seconds for item in program.selected_items), 300)
        self.assertEqual(program.budget_scope, "stop_explanation_content_only")
        self.assertEqual(program.allocated_content_seconds, sum(item.planned_seconds for item in program.selected_items))
        self.assertEqual(program.allocated_content_seconds + program.unallocated_content_seconds, 300)
        self.assertTrue(all(item.rag_query_hints for item in program.selected_items))
        self.assertTrue(all(not item.research_summary_card_ids for item in program.selected_items))

    def test_same_input_has_identical_stable_program(self):
        first = plan_stop_program("stop_front_courtyard_center", 240, ["灰塑"], "standard")
        second = plan_stop_program("stop_front_courtyard_center", 240, ["灰塑"], "standard")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual([item.role for item in first.selected_items], ["核心观察", "工艺或题材对照"])

    def test_detail_level_and_budget_limit_selection_to_one_to_three_items(self):
        short = plan_stop_program("label_moon_platform", 300, detail_level="short")
        standard = plan_stop_program("label_moon_platform", 300, detail_level="standard")
        deep = plan_stop_program("label_moon_platform", 300, detail_level="deep")
        self.assertEqual(len(short.selected_items), 1)
        self.assertEqual(len(standard.selected_items), 2)
        self.assertEqual(len(deep.selected_items), 3)

    def test_interest_changes_ranking_with_stable_id_as_tie_breaker(self):
        cards = {
            "test_stop": {
                "node_id": "test_stop",
                "display_name": "测试点",
                "ornaments": [
                    {"ornament_id": "orn_001", "name": "甲", "craft": "木雕"},
                    {"ornament_id": "orn_002", "name": "乙", "craft": "灰塑"},
                    {"ornament_id": "orn_003", "name": "丙", "craft": "石雕"},
                ],
                "rag_queries": ["甲 是什么装饰", "乙 是什么装饰", "丙 是什么装饰"],
            }
        }
        with patch("guide_program_planner.load_guide_cards", return_value=cards):
            plain = plan_stop_program("test_stop", 120, detail_level="short")
            plaster = plan_stop_program("test_stop", 120, interests=["灰塑"], detail_level="short")
        self.assertEqual(plain.selected_items[0].ornament_id, "orn_001")
        self.assertEqual(plaster.selected_items[0].ornament_id, "orn_002")
        self.assertIn("灰塑", plaster.selected_items[0].selection_reason)

    def test_unknown_point_and_invalid_inputs_are_rejected(self):
        with self.assertRaises(GuideProgramError):
            plan_stop_program("not_reviewed", 300)
        with self.assertRaises(GuideProgramError):
            plan_stop_program("label_moon_platform", 0)
        with self.assertRaises(GuideProgramError):
            plan_stop_program("label_moon_platform", 300, detail_level="verbose")

    def test_empty_candidate_card_returns_a_safe_auditable_program(self):
        cards = {
            "empty_stop": {
                "node_id": "empty_stop", "display_name": "空候选点", "ornaments": [], "rag_queries": []
            }
        }
        with patch("guide_program_planner.load_guide_cards", return_value=cards):
            program = plan_stop_program("empty_stop", 120, interests=["灰塑"], detail_level="deep")
        self.assertEqual(program.status, "no_reviewed_candidates")
        self.assertEqual(program.selected_items, ())
        self.assertEqual(program.candidate_count, 0)


if __name__ == "__main__":
    unittest.main()
