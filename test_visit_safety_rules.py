"""Tests for deterministic visitor-safety selection and rendering."""

from __future__ import annotations

import unittest

from visit_safety_rules import (
    answer_visit_safety_question,
    is_visit_safety_question,
    load_visit_safety_rules,
)


class VisitSafetyRulesTests(unittest.TestCase):
    def test_all_reviewed_prohibitions_load_from_the_knowledge_source(self) -> None:
        rules = load_visit_safety_rules()
        self.assertEqual(
            set(rules),
            {
                "smoking",
                "touching",
                "flash",
                "commercial_photo",
                "drone",
                "food",
            },
        )
        self.assertIn("全场禁烟", rules["smoking"])
        self.assertIn("建筑构件", rules["touching"])
        self.assertIn("闪光灯", rules["flash"])
        self.assertIn("商业拍摄", rules["commercial_photo"])
        self.assertIn("全域禁飞", rules["drone"])
        self.assertIn("庭院休息区", rules["food"])

    def test_queries_select_only_the_relevant_reviewed_rules(self) -> None:
        cases = {
            "这里可以抽烟吗？": "smoking",
            "能摸一下木雕吗？": "touching",
            "室内拍照可以开闪光灯吗？": "flash",
            "可以来这里商拍吗？": "commercial_photo",
            "我想带无人机去拍陈家祠，可以直接飞吗？": "drone",
            "奶茶能带进展厅吗？": "food",
        }
        for query, expected_rule in cases.items():
            with self.subTest(query=query):
                self.assertTrue(is_visit_safety_question(query))
                answer = answer_visit_safety_question(query)
                self.assertIsNotNone(answer)
                self.assertIn(expected_rule, answer["rule_ids"])
                self.assertTrue(answer["verified"])

    def test_drone_answer_is_conclusion_first_and_does_not_leak_internals(self) -> None:
        answer = answer_visit_safety_question(
            "我想带无人机去拍陈家祠，可以直接飞吗？"
        )
        self.assertTrue(answer["message"].startswith("不可以直接使用无人机航拍"))
        self.assertIn("全域禁飞", answer["message"])
        for forbidden in (".md", "03_visit_services", "S0", "http", "chunk"):
            self.assertNotIn(forbidden, answer["message"])

    def test_food_answer_preserves_the_courtyard_exception(self) -> None:
        answer = answer_visit_safety_question("可以带食物进展厅吗？")
        self.assertIn("不能带入展厅内部", answer["message"])
        self.assertIn("庭院休息区", answer["message"])

    def test_unrelated_question_is_not_claimed(self) -> None:
        self.assertFalse(is_visit_safety_question("木雕是怎么制作的？"))
        self.assertIsNone(answer_visit_safety_question("木雕是怎么制作的？"))


if __name__ == "__main__":
    unittest.main()
