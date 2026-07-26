"""Offline B3.1 tests for visitor-safe guide narration."""

from __future__ import annotations

import unittest

from guide_narration import compose_guide_narration
from guide_program_planner import SelectedItem, StopProgram


class GuideNarrationTests(unittest.TestCase):
    def setUp(self):
        first = SelectedItem(
            "orn_001", "百鸟朝凤", "灰塑", "核心观察", 120, "审核选择",
            ("百鸟朝凤 灰塑 特点",), raw_location="首进西路北面", observation_location="首进西路北面",
            location_source="ornament_spatial_mapping_v1",
        )
        second = SelectedItem(
            "orn_002", "石狮子", "石雕", "工艺对照", 90, "审核选择",
            ("石狮子 石雕 特点",), comparison_reason="与核心对象的灰塑作工艺对照，帮助观察两类材料和构件处理的差异",
        )
        self.program = StopProgram(
            "test_stop", "测试点", 300, (), "standard", (first, second), 2,
            allocated_content_seconds=210, unallocated_content_seconds=90,
        )
        self.evidence = {
            "orn_001": [{"document": "08_ornament_items.md", "source_ids": ["S11"], "content": "百鸟朝凤是灰塑装饰题材。它表现凤凰与群鸟的组合。"}],
            "orn_002": [{"document": "07_ornament_crafts.md", "source_ids": ["S10"], "content": "石雕可用于栏杆等建筑构件。其耐候性适应岭南环境。"}],
        }

    def test_standard_message_hides_internal_schedule_and_raw_evidence_paths(self):
        narration = compose_guide_narration(self.program, self.evidence)
        self.assertIn("现在来到测试点", narration.visitor_message)
        self.assertIn("百鸟朝凤", narration.visitor_message)
        self.assertNotIn("08_ornament_items.md", narration.visitor_message)
        self.assertNotIn("核心观察", narration.visitor_message)
        self.assertNotIn("计划约", narration.visitor_message)
        self.assertNotIn("审核位置", narration.visitor_message)
        self.assertNotIn("类型：", narration.visitor_message)
        self.assertNotIn("简介：", narration.visitor_message)
        self.assertIn("首进西路北面", narration.visitor_message)
        self.assertIn("这里特意选它作对照", narration.visitor_message)
        self.assertEqual(narration.source_ids, ("S10", "S11"))

    def test_detail_message_is_meaningfully_different_from_standard(self):
        standard = compose_guide_narration(self.program, self.evidence)
        detailed = compose_guide_narration(self.program, self.evidence, detailed=True)
        self.assertNotEqual(standard.visitor_message, detailed.visitor_message)
        self.assertIn("再看细一点", detailed.visitor_message)
        self.assertIn("如果您愿意", detailed.visitor_message)

    def test_incomplete_chunk_is_not_emitted_as_a_cut_sentence(self):
        evidence = {"orn_001": [{"source_ids": ["S11"], "content": "这是一段没有终止符的原始内容"}], "orn_002": []}
        narration = compose_guide_narration(self.program, evidence)
        self.assertIn("这是一段没有终止符的原始内容。", narration.visitor_message)
        self.assertNotIn("…", narration.visitor_message)

    def test_rejected_optional_llm_output_falls_back_to_safe_renderer(self):
        narration = compose_guide_narration(self.program, self.evidence, narrator=lambda _: "08_ornament_items.md 原始内容")
        self.assertFalse(narration.used_llm)
        self.assertEqual(narration.fallback_reason, "narrator_output_rejected")
        self.assertNotIn("08_ornament_items.md", narration.visitor_message)


if __name__ == "__main__":
    unittest.main()
