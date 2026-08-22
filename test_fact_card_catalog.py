"""Coverage checks for the first P0 FactCard authoring batch."""

from __future__ import annotations

import unittest

from fact_card_catalog import answer_high_frequency_fact_cards, load_high_frequency_fact_cards
from fact_card_renderer import render_fact_cards


class FactCardCatalogTests(unittest.TestCase):
    def test_p0_catalog_covers_opening_transport_ticketing_and_visit_service(self):
        catalog = load_high_frequency_fact_cards()
        self.assertEqual(
            {card.domain for card in catalog.cards},
            {"opening_hours", "transport", "ticketing", "visit_service"},
        )
        self.assertEqual(len({card.card_id for card in catalog.cards}), len(catalog.cards))
        self.assertTrue(all(card.runtime_status == "enabled" for card in catalog.cards))

    def test_each_card_is_renderable_without_model_or_retrieval(self):
        for card in load_high_frequency_fact_cards().cards:
            with self.subTest(card_id=card.card_id):
                answer = render_fact_cards((card,), requested_question_types=card.question_types)
                self.assertEqual(answer.status, "complete")
                self.assertIn(card.fact_statements[0], answer.message)
                self.assertNotIn(".md", answer.message)
                self.assertNotIn("source_ids", answer.message)

    def test_photo_rule_card_is_rule_focused_not_photo_spot_recommendation(self):
        card = next(card for card in load_high_frequency_fact_cards().cards if card.card_id == "visit_service_photo_rule")
        answer = render_fact_cards((card,), requested_question_types=("rule",))
        self.assertIn("闪光灯", answer.message)
        self.assertNotIn("拍摄位置", answer.message)


    def test_invoice_after_sale_question_does_not_get_intercepted_as_plain_refund(self):
        self.assertIsNone(answer_high_frequency_fact_cards("\u53d1\u7968\u5f00\u4e86\u8fd8\u80fd\u9000\u7968\u5417\uff1f"))

    def test_composite_opening_and_purchase_question_keeps_confirmed_cards(self):
        answer = answer_high_frequency_fact_cards(
            "\u6211\u4e0b\u53483\u70b9\u5230\uff0c\u8fd8\u80fd\u4e70\u7968\u8fdb\u53bb\u5417\uff1f\u901b\u5230\u95ed\u9986\u6765\u5f97\u53ca\u5417\uff1f"
        )
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(answer.answered_card_ids, ("opening_hours_regular", "ticketing_purchase_method"))
        self.assertTrue(answer.partial)
        self.assertIn("https://wx.gzcjc.com.cn", answer.message)

    def test_student_ticket_compound_question_is_partial_instead_of_a_global_fallback(self):
        answer = answer_high_frequency_fact_cards(
            "\u5b66\u751f\u7968\u600e\u4e48\u4e70\uff1f\u8981\u5e26\u5b66\u751f\u8bc1\u5417\uff1f\u5f53\u5929\u4e70\u884c\u4e0d\u884c\uff1f"
        )
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(answer.answered_card_ids, ("ticketing_purchase_method",))
        self.assertTrue(answer.partial)
        self.assertIn("eligibility", answer.unanswered_question_types)
        self.assertIn("availability", answer.unanswered_question_types)
        self.assertIn("优惠资格或所需证件", answer.message)
        self.assertIn("当天可用性、余票或现场服务情况", answer.message)
        self.assertNotIn("eligibility", answer.message)

    def test_standalone_purchase_question_stays_with_the_existing_controlled_flow(self):
        self.assertIsNone(answer_high_frequency_fact_cards("\u600e\u4e48\u8d2d\u7968\uff1f"))


if __name__ == "__main__":
    unittest.main()
