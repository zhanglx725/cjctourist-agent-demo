"""Offline tests for broad, evidence-grounded controlled knowledge QA."""

from __future__ import annotations

import unittest

from controlled_knowledge_query import (
    ControlledKnowledgePlan,
    OFFICIAL_TICKETING_URL,
    build_controlled_retrieval_query,
    filter_plan_evidence,
    grounded_answer_prompt,
    identify_controlled_knowledge_plan,
    is_public_visitor_message,
    public_visitor_message_or_fallback,
    render_controlled_knowledge_answer,
)


class ControlledKnowledgeQueryTests(unittest.TestCase):
    def test_title_like_invoice_requests_use_one_closed_ticketing_plan(self):
        cases = (
            ("团体发票", "rule"),
            ("团体发票怎么办？", "method"),
            ("团队发票", "rule"),
            ("团队订单电子发票规则", "rule"),
            ("团队票怎么开发票", "method"),
            ("发票怎么申请？", "method"),
            ("多久以内可以开发票？", "rule"),
            ("开票后还能改吗", "rule"),
            ("开票以后可以退票吗？", "rule"),
            ("发票开了还能退吗？", "rule"),
            ("已经开票还能退票吗？", "rule"),
        )
        for text, question_type in cases:
            with self.subTest(text=text):
                plan = identify_controlled_knowledge_plan(text)
                self.assertIsNotNone(plan)
                self.assertEqual(plan.domain, "ticketing")
                self.assertEqual(plan.question_type, question_type)
                self.assertEqual(plan.categories, ("ticketing_snapshot",))
                self.assertEqual(plan.subject_text, text.rstrip("？?。！!"))
        self.assertIsNone(
            identify_controlled_knowledge_plan(
                "帮我规划路线，再说说团队订单电子发票规则"
            )
        )
        # Team-ticket refund questions are a different reviewed fact and
        # must not be claimed by the invoice plan merely because they contain
        # 团队/团体 context and 退字样.
        self.assertIsNone(
            identify_controlled_knowledge_plan("团队票没用能退吗？")
        )

    def test_child_ticket_eligibility_uses_a_closed_ticketing_plan(self):
        for text in (
            "儿童票对身高和年龄有要求吗",
            "儿童票有年龄或身高要求吗？",
            "未成年人购票的身高条件是什么",
        ):
            with self.subTest(text=text):
                plan = identify_controlled_knowledge_plan(text)
                self.assertIsNotNone(plan)
                self.assertEqual(plan.domain, "ticketing")
                self.assertEqual(plan.question_type, "eligibility")

    def test_ticket_purchase_method_uses_a_closed_ticketing_plan(self):
        for text in ("怎么购票", "怎么买票？", "如何预约", "购票方式是什么"):
            with self.subTest(text=text):
                plan = identify_controlled_knowledge_plan(text)
                self.assertIsNotNone(plan)
                self.assertEqual(plan.domain, "ticketing")
                self.assertEqual(plan.question_type, "method")

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

    def test_each_internal_identifier_rejects_the_entire_model_candidate(self):
        plan = ControlledKnowledgePlan(
            "ornament_item", "story", "三顾茅庐", "brief"
        )
        evidence = [{"category": "ornament_item", "content": "故事证据"}]
        forbidden_candidates = (
            "来源：S10",
            "S11",
            "S123",
            "参见 07_ornament_crafts.md",
            "http://example.com",
            "https://example.com",
            "source_ids",
            "used_source_ids",
            "title_path",
            "chunk_id",
            "node_id",
            "retrieval_methods",
            "knowledge_base",
            "label_moon_platform",
            "stop_front_courtyard_center",
            "orn_080",
            "term_stone_carving",
        )
        for candidate in forbidden_candidates:
            with self.subTest(candidate=candidate):
                message = render_controlled_knowledge_answer(
                    plan,
                    evidence,
                    lambda _: f"这是不应展示的候选：{candidate}",
                )
                self.assertIn("无法把证据安全整理成游客答案", message)
                self.assertNotIn(candidate, message)

    def test_safe_model_candidate_is_returned_without_losing_scoped_evidence(self):
        plan = ControlledKnowledgePlan(
            "ornament_item", "story", "三顾茅庐", "brief"
        )
        evidence = [{"category": "ornament_item", "content": "故事证据"}]
        message = render_controlled_knowledge_answer(
            plan, evidence, lambda _: "刘备三次拜访诸葛亮，表达了诚心求贤。"
        )
        self.assertIn("刘备三次拜访诸葛亮", message)
        self.assertEqual(filter_plan_evidence(plan, evidence), evidence)

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

    def test_reviewed_invoice_rule_is_deterministic_and_natural(self):
        plan = identify_controlled_knowledge_plan("团队订单电子发票规则")
        evidence = [
            {
                "category": "ticketing_snapshot",
                "content": (
                    "团队订单电子发票规则：购买后 30 日内可申请；"
                    "发票开具后不可修改且不能退票。"
                ),
            },
            {
                "category": "basic_info",
                "content": "无关场馆地址。",
            },
        ]

        def forbidden(_: str) -> str:
            self.fail("reviewed invoice rule must not depend on model synthesis")

        message = render_controlled_knowledge_answer(plan, evidence, forbidden)
        self.assertIn("团队订单的电子发票", message)
        self.assertIn("购买后 30 日内", message)
        self.assertIn("不能修改", message)
        self.assertIn("不能办理退票", message)
        self.assertIn("官方小程序订单页面", message)
        self.assertNotIn("ticketing_snapshot", message)
        self.assertNotIn("本地规则快照", message)
        self.assertTrue(is_public_visitor_message(message))

    def test_child_ticket_rule_is_rendered_from_complete_evidence_without_model(self):
        plan = identify_controlled_knowledge_plan("儿童票对身高和年龄有要求吗")
        evidence = [{
            "category": "ticketing_snapshot",
            "content": (
                "半票：适用于 6 周岁（不含）至 18 周岁未成年人、"
                "身高 1.3 米以上儿童。免预约购票/凭证入场："
                "未满 6 周岁儿童、身高 1.3 米（含）以下儿童。"
            ),
        }]

        def forbidden(_: str) -> str:
            self.fail("complete child ticket evidence must not depend on model synthesis")

        message = render_controlled_knowledge_answer(plan, evidence, forbidden)
        self.assertIn("6 周岁（不含）至 18 周岁", message)
        self.assertIn("身高 1.3 米以上", message)
        self.assertIn("未满 6 周岁", message)
        self.assertIn("身高 1.3 米（含）以下", message)
        self.assertIn("官方小程序", message)
        self.assertTrue(is_public_visitor_message(message))

    def test_ticket_purchase_method_is_rendered_from_reviewed_channel_without_model(self):
        plan = identify_controlled_knowledge_plan("怎么购票")
        evidence = [{
            "category": "ticketing_snapshot",
            "content": (
                "官方预约/购票渠道：微信公众号“广东民间工艺博物馆”服务号。"
                "馆方未授权第三方销售门票，或提供“讲解导览 + 门票预约”套餐。"
            ),
        }]

        def forbidden(_: str) -> str:
            self.fail("reviewed purchase channel must not depend on model synthesis")

        message = render_controlled_knowledge_answer(plan, evidence, forbidden)
        self.assertIn("微信公众号“广东民间工艺博物馆”服务号", message)
        self.assertIn("未授权第三方", message)
        self.assertIn(OFFICIAL_TICKETING_URL, message)
        self.assertIn("当日页面", message)
        self.assertTrue(is_public_visitor_message(message))

    def test_public_output_gate_rejects_internal_descriptions_for_every_domain(self):
        domain_cases = (
            "site_overview", "history_architecture", "visit_service", "ticketing",
            "ornament_craft", "ornament_item",
        )
        for domain in domain_cases:
            with self.subTest(domain=domain):
                plan = ControlledKnowledgePlan(domain, "feature", "陈家祠", "brief")
                message = render_controlled_knowledge_answer(
                    plan,
                    [{"category": plan.categories[0], "content": "现有资料中的事实。", "source_ids": ["S07"]}],
                    lambda _: "来自本地快照 06_ticketing_rules.md（来源：S07）",
                )
                self.assertIn("无法把证据安全整理成游客答案", message)
                self.assertNotIn("本地快照", message)
                self.assertNotIn("S07", message)

    def test_incomplete_invoice_evidence_fails_closed_without_model(self):
        plan = identify_controlled_knowledge_plan("开票后还能改吗")

        def forbidden(_: str) -> str:
            self.fail("incomplete reviewed invoice evidence must fail closed")

        message = render_controlled_knowledge_answer(
            plan,
            [
                {
                    "category": "ticketing_snapshot",
                    "content": "电子发票可在购买后 30 日内申请。",
                }
            ],
            forbidden,
        )
        self.assertIn("资料不足", message)
        self.assertIn("不作推测", message)

    def test_shared_public_boundary_rejects_internal_metadata_without_false_positives(self):
        forbidden_candidates = (
            "请参见 06_ticketing_rules.md。",
            "资料位于 data/chen_clan_academy/knowledge/01_basic_info.md。",
            r"资料位于 C:\\workspace\\data\\01_basic_info.md。",
            "来源：S07。",
            "source_ids: S11",
            "对象编号 orn_005，节点 stop_front_courtyard_center。",
            "详情见 https://example.com/internal。",
            "这是本地快照，资料整理日期为 2025-01-01。",
        )
        for candidate in forbidden_candidates:
            with self.subTest(candidate=candidate):
                self.assertFalse(is_public_visitor_message(candidate))
                fallback = public_visitor_message_or_fallback(candidate)
                self.assertTrue(fallback)
                self.assertTrue(is_public_visitor_message(fallback))
                self.assertNotEqual(fallback, candidate)

        allowed_candidates = (
            "建议游览 30/60 分钟，可按时间选择。",
            "这件作品采用 S 形构图，线条富有变化。",
            "陈氏书院于 1888 年开始筹建。",
            "VIP 游客也应遵守现场安全要求。",
            "可重点观察独角狮、福禄寿与石狮子的造型。",
        )
        for candidate in allowed_candidates:
            with self.subTest(candidate=candidate):
                self.assertTrue(is_public_visitor_message(candidate))
                self.assertEqual(public_visitor_message_or_fallback(candidate), candidate)

    def test_only_the_reviewed_official_ticketing_url_is_allowed_in_public_text(self):
        allowed = f"购票入口：{OFFICIAL_TICKETING_URL}"
        self.assertTrue(is_public_visitor_message(allowed))
        self.assertFalse(is_public_visitor_message("https://example.com"))
        self.assertFalse(
            is_public_visitor_message(f"{OFFICIAL_TICKETING_URL}/unexpected")
        )


if __name__ == "__main__":
    unittest.main()
