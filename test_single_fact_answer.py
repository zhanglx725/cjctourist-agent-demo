from __future__ import annotations

import unittest

from single_fact_answer import (
    identify_single_fact_kind,
    render_single_fact_answer,
    single_fact_categories,
)


HISTORY_EVIDENCE = {
    "category": "history_architecture",
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
    "category": "basic_info",
    "document": "01_basic_info.md",
    "title_path": ["基础信息", "信息卡"],
    "source_ids": ["S01"],
    "content": (
        "- 场馆名称：广东民间工艺博物馆\n"
        "- 馆址：陈家祠（陈氏书院）\n"
        "- 地址：广州市荔湾区中山七路恩龙里 34 号"
    ),
}
IDENTITY_WORKAROUND_EVIDENCE = {
    "category": "ticketing_snapshot",
    "document": "06_ticketing_rules.md",
    "title_path": ["购票、预约与入馆规则", "检票方式"],
    "source_ids": ["S07"],
    "content": (
        "未携带身份证件者，可到综合服务处出示电子身份证或其他有效证件"
        "换取实体票。使用优惠票或免票入场者，应按要求出示相应证件供查验。"
    ),
}
IDENTITY_ORIGINAL_ONLY_EVIDENCE = {
    "category": "visit_service",
    "document": "03_visit_services.md",
    "title_path": ["游览服务与参观提示", "服务设施"],
    "source_ids": ["S05"],
    "content": "预约游客入馆时须出示本人有效身份证原件核验。",
}
MUSEUM_HISTORY_EVIDENCE = {
    "category": "history_architecture",
    "document": "02_history_architecture.md",
    "title_path": ["历史、建筑与文化特色", "百年历史时间线"],
    "source_ids": ["S02"],
    "content": (
        "1959 年以陈氏书院为馆址成立广东民间工艺馆。"
        "广东民间工艺馆于 1983 年 2 月 13 日复馆并重新对外开放。"
        "1994 年“广东民间工艺馆”更名为“广东民间工艺博物馆”。"
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
        self.assertEqual(
            identify_single_fact_kind("陈家祠从筹建到落成大约经历了多久？"),
            "construction_duration",
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
        museum_cases = (
            (
                "广东民间工艺博物馆是什么时候在这里成立的？",
                "museum_establishment",
            ),
            ("广东民间工艺馆哪一年设立？", "museum_establishment"),
            ("广东民间工艺馆何时复馆？", "museum_reopening"),
            (
                "广东民间工艺馆什么时候重新对外开放？",
                "museum_reopening",
            ),
            (
                "广东民间工艺馆什么时候更名为广东民间工艺博物馆？",
                "museum_renaming",
            ),
        )
        for query, expected_kind in museum_cases:
            with self.subTest(query=query):
                self.assertEqual(
                    identify_single_fact_kind(query), expected_kind
                )
                self.assertEqual(
                    single_fact_categories(query), ["history_architecture"]
                )
        self.assertIsNone(
            identify_single_fact_kind("广东民间工艺博物馆是什么？")
        )
        for query in (
            "订了票忘带身份证，能不能进？",
            "没有带身份证可以入馆吗？",
            "证件丢了还能检票进馆吗？",
            "可以用电子身份证入馆吗？",
            "身份证照片能代替原件检票吗？",
            "没带身份证怎么办？",
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    identify_single_fact_kind(query),
                    "identity_admission_workaround",
                )
                self.assertEqual(
                    single_fact_categories(query),
                    ["ticketing_snapshot", "visit_service"],
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
            "陈家祠于 1888 年开始筹建。这一年份指筹建启动，不是落成年份。",
        )

    def test_address_answer_is_compact_and_evidence_bounded(self):
        result = render_single_fact_answer(
            "陈家祠在哪里？", [HISTORY_EVIDENCE, ADDRESS_EVIDENCE]
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.source_ids, ("S01",))
        self.assertEqual(
            result.message,
            "陈家祠的地址是广州市荔湾区中山七路恩龙里 34 号。",
        )

    def test_duration_is_a_deterministic_evidence_bounded_year_difference(self):
        result = render_single_fact_answer(
            "陈家祠从筹建到落成大约经历了多久？", [HISTORY_EVIDENCE]
        )
        self.assertTrue(result.ok)
        self.assertIn("5 至 6 年", result.message)
        self.assertIn("1893 年口径约 5 年", result.message)
        self.assertIn("1894 年口径约 6 年", result.message)
        self.assertEqual(result.calculation["operation"], "year_difference")
        self.assertTrue(result.calculation["deterministic"])
        self.assertNotRegex(result.message, r"(?<![A-Za-z0-9])S\d+")

    def test_recognized_fact_fails_closed_without_matching_evidence(self):
        result = render_single_fact_answer(
            "陈家祠哪一年建成？",
            [{"source_ids": ["S11"], "content": "独角狮是一件灰塑装饰。"}],
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertIn("资料不足", result.message)
        self.assertNotIn("独角狮", result.message)

    def test_museum_history_milestones_are_kept_distinct(self):
        establishment = render_single_fact_answer(
            "广东民间工艺博物馆是什么时候在这里成立的？",
            [MUSEUM_HISTORY_EVIDENCE],
        )
        self.assertTrue(establishment.ok)
        self.assertIn("前身“广东民间工艺馆”于 1959 年", establishment.message)
        self.assertIn("1994 年", establishment.message)
        self.assertIn("机构成立时间", establishment.message)
        self.assertIn("现名启用时间", establishment.message)

        reopening = render_single_fact_answer(
            "广东民间工艺馆何时复馆？", [MUSEUM_HISTORY_EVIDENCE]
        )
        self.assertTrue(reopening.ok)
        self.assertIn("1983 年 2 月 13 日", reopening.message)
        self.assertIn("不是机构最初成立或更名的日期", reopening.message)

        renaming = render_single_fact_answer(
            "广东民间工艺馆哪一年更名？", [MUSEUM_HISTORY_EVIDENCE]
        )
        self.assertTrue(renaming.ok)
        self.assertIn("1994 年", renaming.message)
        self.assertIn("1959 年是机构成立时间", renaming.message)
        for result in (establishment, reopening, renaming):
            self.assertEqual(result.source_ids, ("S02",))
            self.assertNotIn(".md", result.message)
            self.assertNotRegex(result.message, r"(?<![A-Za-z0-9])S\d+")

    def test_museum_history_question_fails_closed_on_generic_definition(self):
        result = render_single_fact_answer(
            "广东民间工艺博物馆是什么时候成立的？",
            [
                {
                    "category": "basic_info",
                    "source_ids": ["S01"],
                    "content": "广东民间工艺博物馆是以陈家祠为馆址的博物馆。",
                }
            ],
        )
        self.assertFalse(result.ok)
        self.assertIn("资料不足", result.message)
        self.assertNotIn("以陈家祠为馆址的博物馆", result.message)

    def test_missing_identity_answer_uses_reviewed_service_desk_workaround(self):
        result = render_single_fact_answer(
            "订了票忘带身份证，能不能进？",
            [IDENTITY_ORIGINAL_ONLY_EVIDENCE, IDENTITY_WORKAROUND_EVIDENCE],
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertIn("有替代处理方式", result.message)
        self.assertIn("综合服务处", result.message)
        self.assertIn("电子身份证或其他有效证件", result.message)
        self.assertIn("换取实体票", result.message)
        self.assertIn("优惠票或免票", result.message)
        self.assertNotIn(".md", result.message)
        self.assertNotRegex(result.message, r"(?<![A-Za-z0-9])S\d+")

    def test_missing_identity_answer_does_not_turn_original_rule_into_a_ban(self):
        result = render_single_fact_answer(
            "订了票忘带身份证，能不能进？",
            [IDENTITY_ORIGINAL_ONLY_EVIDENCE],
        )
        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertIn("资料不足", result.message)
        self.assertIn("不能仅凭", result.message)
        self.assertNotIn("无法入馆", result.message)


if __name__ == "__main__":
    unittest.main()
