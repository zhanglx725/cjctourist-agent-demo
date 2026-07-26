"""Offline B2 tests for StopProgram budget and diversity policy."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from guide_program_planner import STOP_PROGRAM_POLICY, plan_stop_program


class GuideProgramBudgetTests(unittest.TestCase):
    def _cards(self):
        return {
            "test_stop": {
                "node_id": "test_stop",
                "display_name": "测试点",
                "ornaments": [
                    {"ornament_id": "orn_001", "name": "福寿灰塑", "craft": "灰塑"},
                    {"ornament_id": "orn_002", "name": "瑞兽灰塑", "craft": "灰塑"},
                    {"ornament_id": "orn_003", "name": "木雕人物故事", "craft": "木雕"},
                ],
                "rag_queries": ["福寿灰塑是什么装饰", "瑞兽灰塑是什么装饰", "木雕人物故事讲什么"],
            }
        }

    def test_budget_boundaries_safely_reduce_item_count_and_never_overrun(self):
        with patch("guide_program_planner.load_guide_cards", return_value=self._cards()):
            brief = plan_stop_program("test_stop", 60, detail_level="deep")
            standard_low = plan_stop_program("test_stop", 149, detail_level="standard")
            standard_two = plan_stop_program("test_stop", 150, detail_level="standard")
            deep_two = plan_stop_program("test_stop", 269, detail_level="deep")
            deep_three = plan_stop_program("test_stop", 270, detail_level="deep")
        self.assertEqual((len(brief.selected_items), brief.status, brief.selected_items[0].role), (1, "brief_overview", "简短概览"))
        self.assertEqual(len(standard_low.selected_items), 1)
        self.assertEqual(len(standard_two.selected_items), 2)
        self.assertEqual(len(deep_two.selected_items), 2)
        self.assertEqual(len(deep_three.selected_items), 3)
        for program in (brief, standard_low, standard_two, deep_two, deep_three):
            self.assertLessEqual(program.allocated_content_seconds, program.budget_seconds)
            self.assertEqual(program.allocated_content_seconds + program.unallocated_content_seconds, program.budget_seconds)

    def test_interest_keeps_relevant_reviewed_object_ahead_of_diversity(self):
        with patch("guide_program_planner.load_guide_cards", return_value=self._cards()):
            program = plan_stop_program("test_stop", 270, interests=["灰塑"], detail_level="deep")
        self.assertEqual(program.selected_items[0].craft, "灰塑")
        self.assertTrue(all(item.ornament_id in {"orn_001", "orn_002", "orn_003"} for item in program.selected_items))

    def test_close_relevance_prefers_new_craft_or_theme_for_diversity(self):
        with patch("guide_program_planner.load_guide_cards", return_value=self._cards()):
            program = plan_stop_program("test_stop", 150, detail_level="standard")
        self.assertEqual([item.ornament_id for item in program.selected_items], ["orn_001", "orn_003"])
        self.assertEqual({item.craft for item in program.selected_items}, {"灰塑", "木雕"})

    def test_policy_and_stable_tie_breaking_produce_identical_output(self):
        self.assertIn("relevance_window", STOP_PROGRAM_POLICY["diversity"])
        with patch("guide_program_planner.load_guide_cards", return_value=self._cards()):
            first = plan_stop_program("test_stop", 270, detail_level="deep")
            second = plan_stop_program("test_stop", 270, detail_level="deep")
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_all_detail_levels_respect_content_budget_not_walking_time(self):
        with patch("guide_program_planner.load_guide_cards", return_value=self._cards()):
            programs = [
                plan_stop_program("test_stop", budget, detail_level=level)
                for budget in (30, 90, 150, 240, 300)
                for level in ("short", "standard", "deep")
            ]
        for program in programs:
            self.assertEqual(program.budget_scope, "stop_explanation_content_only")
            self.assertLessEqual(sum(item.planned_seconds for item in program.selected_items), program.budget_seconds)


if __name__ == "__main__":
    unittest.main()
