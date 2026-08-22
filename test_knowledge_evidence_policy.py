"""Safety, ranking and sizing tests for expanded knowledge evidence."""

from __future__ import annotations

import unittest

from controlled_knowledge_query import ControlledKnowledgePlan, filter_plan_evidence, grounded_answer_prompt
from knowledge_evidence_policy import (
    evidence_is_safe_for_domain,
    retrieval_limit_for_plan,
    retrieval_limit_for_question,
)
from narration_coverage import commit_introductions, empty_narration_coverage


def _entry(document: str, content: str, source: str = "S20") -> dict:
    return {
        "document": document,
        "category": "history_architecture",
        "title_path": ["资料", "测试"],
        "source_ids": [source],
        "content": content,
    }


class KnowledgeEvidencePolicyTests(unittest.TestCase):
    def test_people_require_attribution_and_the_people_document(self):
        safe = _entry(
            "10_people_builders_craftspeople.md",
            "馆方公开采访记载，邵成村曾参与陈家祠灰塑维护。",
        )
        unsafe = _entry(
            "10_people_builders_craftspeople.md",
            "有一位岭南工匠完成了所有灰塑。",
        )
        self.assertTrue(evidence_is_safe_for_domain("people_craftspeople", safe))
        self.assertFalse(evidence_is_safe_for_domain("people_craftspeople", unsafe))

    def test_conservation_requires_attribution_and_time_boundary(self):
        historical = _entry(
            "11_architectural_conservation.md",
            "馆方2019年资料记载曾采用相关监测措施；当前状态仍需以最新资料为准。",
        )
        timeless = _entry(
            "11_architectural_conservation.md",
            "馆方使用北斗系统实时监测。",
        )
        self.assertTrue(evidence_is_safe_for_domain("architectural_conservation", historical))
        self.assertFalse(evidence_is_safe_for_domain("architectural_conservation", timeless))

    def test_literary_card_requires_complete_citation_fields_and_relation(self):
        safe = {
            "document": "13_literary_citation_cards.md", "source_ids": ["S30"],
            "content": (
                "原文：如南山之寿。作者：诗经不署个人作者。篇名：天保。"
                "版本或来源：核验本。对应装饰或点位：九如图。"
                "是否为直接相关：是。是否允许逐字引用：允许。"
            ),
        }
        missing_relation = {**safe, "content": safe["content"].replace("是否为直接相关：是。", "")}
        self.assertTrue(evidence_is_safe_for_domain("literary_citation", safe))
        self.assertFalse(evidence_is_safe_for_domain("literary_citation", missing_relation))

    def test_controlled_filter_rejects_unsafe_people_material(self):
        plan = ControlledKnowledgePlan("people_craftspeople", "person", "有哪些工匠", "brief")
        evidence = [
            _entry("10_people_builders_craftspeople.md", "传说有一位工匠。"),
            _entry("10_people_builders_craftspeople.md", "馆方公开采访记载，邵成村参与过维护。", "S21"),
        ]
        filtered = filter_plan_evidence(plan, evidence)
        self.assertEqual(len(filtered), 1)
        self.assertIn("邵成村", filtered[0]["content"])

    def test_prompts_preserve_literary_and_conservation_boundaries(self):
        literary = ControlledKnowledgePlan("literary_citation", "other", "相关诗句", "brief")
        conservation = ControlledKnowledgePlan("architectural_conservation", "other", "当前监测", "brief")
        self.assertIn("借用诗意", grounded_answer_prompt(literary, []))
        self.assertIn("当前状态", grounded_answer_prompt(conservation, []))

    def test_retrieval_pool_scales_with_detail_and_breadth(self):
        self.assertEqual(retrieval_limit_for_plan("brief", 1), 4)
        self.assertEqual(retrieval_limit_for_plan("detailed", 1), 8)
        self.assertEqual(retrieval_limit_for_question("灰塑是什么"), 4)
        self.assertEqual(retrieval_limit_for_question("详细讲讲工匠、保护和制作工序"), 8)
        self.assertEqual(retrieval_limit_for_question("保护修缮和制作工序有什么联系"), 6)

    def test_dimension_coverage_is_idempotent_without_changing_public_schema_fields(self):
        record = {
            "subject_kind": "dimension", "subject_id": "knowledge_deadbeef",
            "source_ids": ["S11"], "introduced_by": "stop_guidance",
            "node_id": "stop_front_courtyard_center", "turn_id": "turn:1",
        }
        first = commit_introductions(empty_narration_coverage(), [record])
        second = commit_introductions(first, [record])
        self.assertEqual(first, second)
        self.assertEqual(first.introduced_craft_ids, ())
        self.assertEqual(first.introduced_ornament_ids, ())
        self.assertEqual(first.introduction_records[0].subject_kind, "dimension")


if __name__ == "__main__":
    unittest.main()
