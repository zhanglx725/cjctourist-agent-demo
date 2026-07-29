from __future__ import annotations

import unittest

from single_fact_answer import (
    identify_single_fact_kind,
    render_single_fact_answer,
    single_fact_categories,
)


HISTORY_EVIDENCE = {
    "document": "02_history_architecture.md",
    "title_path": ["历史、建筑与文化特色", "历史沿革"],
    "source_ids": ["S02", "S04"],
    "content": (
        "- **筹建背景**：1888 年，陈氏书院建祠公所成立并开始筹建。"
        "- **建成年份的来源差异**：馆方历史页面写“1893 年落成”；"
        "广州市文化广电旅游局页面写“1888 年筹建、1894 年建成”。"
    ),
}
ADDRESS_EVIDENCE = {
    "document": "01_basic_info.md",
    "title_path": ["基础信息", "信息卡"],
    "source_ids": ["S01"],
    "content": (
        "- 场馆名称：广东民间工艺博物馆\n"
        "- 馆址：陈家祠（陈氏书院）\n"
        "- 地址：广州市荔湾区中山七路恩龙里 34 号"
    ),
}


class SingleFactAnswerTests(unittest.TestCase):
    def test_only_explicit_reviewed_fact_shapes_are_recognized(self):
        self.assertEqual(
            identify_single_fact_kind("陈家祠是什么时候建成的？"),
            "construction_completion",
        )
        self.assertEqual(
            identify_single_fact_kind("陈氏书院哪一年开始筹建？"),
            "construction_start",
        )
        self.assertEqual(
            identify_single_fact_kind("陈家祠何时建成？"),
            "construction_completion",
        )
        self.assertEqual(
            identify_single_fact_kind("陈家祠建于哪一年？"),
            "construction_completion",
        )
        self.assertEqual(
            identify_single_fact_kind("陈家祠具体地址在哪里？"),
            "site_address",
        )
        self.assertIsNone(identify_single_fact_kind("铜雀台是什么时候建成的？"))
        self.assertIsNone(identify_single_fact_kind("详细讲讲陈家祠"))
        self.assertEqual(
            single_fact_categories("陈家祠什么时候建成？"),
            ["history_architecture"],
        )
        self.assertEqual(
            single_fact_categories("陈家祠在哪里？"),
            ["basic_info"],
        )
        self.assertIsNone(single_fact_categories("详细讲讲陈家祠"))

    def test_completion_answer_leads_with_conclusion_and_preserves_source_conflict(self):
        result = render_single_fact_answer(
            "陈家祠在哪一年建成？", [HISTORY_EVIDENCE]
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(result.source_ids, ("S02", "S04"))
        self.assertIn("1888 年开始筹建", result.message)
        self.assertIn("1893 年落成", result.message)
        self.assertIn("1894 年建成", result.message)
        self.assertIn("不宜把其中一个年份作为唯一结论", result.message)
        for token in (".md", "title_path", "source_ids", "chunk_id"):
            self.assertNotIn(token, result.message)

    def test_start_question_returns_only_supported_start_fact(self):
        result = render_single_fact_answer(
            "陈家祠什么时候开始筹建？", [HISTORY_EVIDENCE]
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            result.message,
            "陈家祠于 1888 年开始筹建。（来源：S02、S04）",
        )

    def test_address_answer_is_compact_and_evidence_bounded(self):
        result = render_single_fact_answer(
            "陈家祠在哪里？", [HISTORY_EVIDENCE, ADDRESS_EVIDENCE]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.source_ids, ("S01",))
        self.assertEqual(
            result.message,
            "陈家祠的地址是广州市荔湾区中山七路恩龙里 34 号。（来源：S01）",
        )

    def test_recognized_fact_fails_closed_without_matching_evidence(self):
        result = render_single_fact_answer(
            "陈家祠哪一年建成？",
            [{"source_ids": ["S11"], "content": "独角狮是一件灰塑装饰。"}],
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertIn("检索证据不足", result.message)
        self.assertNotIn("独角狮", result.message)


if __name__ == "__main__":
    unittest.main()
