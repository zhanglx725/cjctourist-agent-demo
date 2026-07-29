"""Offline tests for broad, evidence-grounded controlled knowledge QA."""

from __future__ import annotations

import unittest

from controlled_knowledge_query import (
    ControlledKnowledgePlan,
    build_controlled_retrieval_query,
    filter_plan_evidence,
    grounded_answer_prompt,
    render_controlled_knowledge_answer,
)


class ControlledKnowledgeQueryTests(unittest.TestCase):
    def test_plan_rejects_values_outside_the_closed_taxonomy(self):
        with self.assertRaises(ValueError):
            ControlledKnowledgePlan(
                "anything", "story", "三顾茅庐", "brief"
            )
        with self.assertRaises(ValueError):
            ControlledKnowledgePlan(
                "ornament_item", "answer_everything", "三顾茅庐", "brief"
            )
        with self.assertRaises(ValueError):
            ControlledKnowledgePlan(
                "ornament_item", "story", "三顾茅庐", "unlimited"
            )
        with self.assertRaises(ValueError):
            ControlledKnowledgePlan(
                "ornament_item", "story", "这个", "brief"
            )

    def test_retrieval_query_is_deterministic_and_code_bounded(self):
        plan = ControlledKnowledgePlan(
            "ornament_item", "story", "三顾茅庐", "detailed"
        )
        first = build_controlled_retrieval_query(plan)
        second = build_controlled_retrieval_query(plan)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("三顾茅庐"))
        self.assertIn("故事", first)
        self.assertNotIn("detailed", first)

    def test_evidence_is_filtered_to_the_reviewed_domain_categories(self):
        plan = ControlledKnowledgePlan(
            "history_architecture", "reason", "陈氏书院", "brief"
        )
        evidence = [
            {"category": "history_architecture", "content": "相关历史"},
            {"category": "basic_info", "content": "无关地址"},
            {"category": "ornament_item", "content": "无关装饰"},
        ]
        self.assertEqual(
            filter_plan_evidence(plan, evidence),
            [evidence[0]],
        )

    def test_prompt_exposes_only_evidence_content_not_internal_metadata(self):
        plan = ControlledKnowledgePlan(
            "ornament_item", "meaning", "独角狮", "brief"
        )
        prompt = grounded_answer_prompt(
            plan,
            [
                {
                    "category": "ornament_item",
                    "document": "08_ornament_items.md",
                    "source_ids": ["S11"],
                    "title_path": ["内部标题"],
                    "content": "独角狮是建筑装饰题材。",
                }
            ],
        )
        self.assertIn("独角狮是建筑装饰题材", prompt)
        self.assertNotIn("08_ornament_items.md", prompt)
        self.assertNotIn("S11", prompt)
        self.assertNotIn("内部标题", prompt)

    def test_no_evidence_fails_closed_without_calling_the_model(self):
        plan = ControlledKnowledgePlan(
            "visit_service", "availability", "行李寄存", "brief"
        )

        def forbidden(_: str) -> str:
            self.fail("model must not run without scoped evidence")

        message = render_controlled_knowledge_answer(plan, [], forbidden)
        self.assertIn("资料不足", message)
        self.assertIn("馆方当日公告", message)

    def test_unsafe_model_output_is_not_shown_to_the_visitor(self):
        plan = ControlledKnowledgePlan(
            "ornament_item", "story", "三顾茅庐", "brief"
        )
        evidence = [{"category": "ornament_item", "content": "故事证据"}]
        message = render_controlled_knowledge_answer(
            plan,
            evidence,
            lambda _: "详见 08_ornament_items.md（来源 S11）",
        )
        self.assertIn("无法把证据安全整理", message)
        self.assertNotIn(".md", message)
        self.assertNotIn("S11", message)

    def test_dynamic_answer_always_carries_the_current_notice(self):
        plan = ControlledKnowledgePlan(
            "ticketing", "eligibility", "学生票", "brief"
        )
        evidence = [{"category": "ticketing_snapshot", "content": "适用条件"}]
        message = render_controlled_knowledge_answer(
            plan,
            evidence,
            lambda _: "学生票的适用条件如下。",
        )
        self.assertIn("馆方当日公告", message)


if __name__ == "__main__":
    unittest.main()
