"""Offline B3.1 tests for visitor-safe guide narration."""

from __future__ import annotations

from dataclasses import replace
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

    def test_detailed_fallback_keeps_story_origin_and_later_evidence_detail(self):
        """The legacy detail path may quote only audited object evidence."""
        item = SelectedItem(
            "orn_051", "踏雪寻梅", "木雕", "核心观察", 120, "审核选择",
            ("踏雪寻梅 木雕 特点",), raw_location="首进中路", observation_location="首进中路",
            location_source="ornament_spatial_mapping_v1",
        )
        program = replace(self.program, selected_items=(item,))
        evidence = {
            "orn_051": [{
                "document": "08_ornament_items.md", "source_ids": ["S11"],
                "title_path": ["陈家祠建筑装饰条目知识库", "踏雪寻梅"],
                "content": "“踏雪寻梅”源自唐代诗人孟浩然的故事。孟浩然冒着大雪骑驴到霸陵赏梅，写下诗篇《南阳阻雪》。",
            }],
        }
        narration = compose_guide_narration(program, evidence, detailed=True)
        self.assertIn("源自唐代诗人孟浩然的故事", narration.visitor_message)
        self.assertIn("骑驴到霸陵赏梅", narration.visitor_message)
        self.assertNotIn("来源：S", narration.visitor_message)
        self.assertEqual(narration.source_ids, ("S11",))

    def test_detailed_fallback_does_not_invent_a_story_from_craft_only_evidence(self):
        item = replace(self.program.selected_items[0], ornament_id="orn_005", name="独角狮", craft="灰塑")
        program = replace(self.program, selected_items=(item,))
        evidence = {
            "orn_005": [{
                "document": "07_ornament_crafts.md", "source_ids": ["S07"],
                "content": "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。制作时可用石灰等材料堆塑。",
            }],
        }
        narration = compose_guide_narration(program, evidence, detailed=True)
        self.assertIn("制作时可用石灰等材料堆塑", narration.visitor_message)
        self.assertNotIn("民间传说", narration.visitor_message)
        self.assertNotIn("辟邪保平安", narration.visitor_message)
        self.assertEqual(narration.source_ids, ("S07",))

    def test_incomplete_chunk_is_not_emitted_as_a_cut_sentence(self):
        evidence = {"orn_001": [{"source_ids": ["S11"], "content": "这是一段没有终止符的原始内容"}], "orn_002": []}
        narration = compose_guide_narration(self.program, evidence)
        self.assertNotIn("这是一段没有终止符的原始内容", narration.visitor_message)
        self.assertIn("未检索到可引用的事实资料", narration.visitor_message)
        self.assertNotIn("…", narration.visitor_message)

    def test_rejected_optional_llm_output_falls_back_to_safe_renderer(self):
        narration = compose_guide_narration(self.program, self.evidence, narrator=lambda _: "08_ornament_items.md 原始内容")
        self.assertFalse(narration.used_llm)
        self.assertEqual(narration.fallback_reason, "narrator_output_rejected")
        self.assertNotIn("08_ornament_items.md", narration.visitor_message)

    def test_fallback_derives_observation_count_and_avoids_generic_repeated_cue(self):
        third = replace(
            self.program.selected_items[1],
            ornament_id="orn_003", name="福禄寿", craft="木雕", observation_location="首进中路",
        )
        evidence = {
            **self.evidence,
            "orn_003": [{"source_ids": ["S11"], "content": "福禄寿表现吉祥题材，构图层次清晰。"}],
        }
        for count in (1, 2, 3):
            with self.subTest(count=count):
                program = replace(self.program, selected_items=(self.program.selected_items + (third,))[:count])
                narration = compose_guide_narration(program, evidence)
                self.assertIn(f"{count}个观察重点", narration.visitor_message)
                self.assertNotIn("两个观察重点", narration.visitor_message)
                self.assertNotIn("留意它与周围构件的关系", narration.visitor_message)

    def test_legacy_detail_renderer_keeps_objects_and_completion_in_flat_sections(self):
        narration = compose_guide_narration(self.program, self.evidence, detailed=True)
        message = narration.visitor_message
        for item in self.program.selected_items:
            self.assertIn(f"【观察对象：{item.name}】", message)
        self.assertIn("【下一步】\n\n", message)
        self.assertFalse(any(line.startswith(("- ", "* ", "  - ", "  * ")) for line in message.splitlines()))


if __name__ == "__main__":
    unittest.main()
