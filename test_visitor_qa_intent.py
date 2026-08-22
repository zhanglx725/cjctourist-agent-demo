"""Regression coverage for public-language high-frequency QA routing."""

from __future__ import annotations

import unittest

from visitor_qa_intent import classify_visitor_qa_intent


class VisitorQaIntentTests(unittest.TestCase):
    def test_opening_and_transport_paraphrases_share_the_fact_card_route(self):
        cases = (
            ("早上七点能进园吗？", "opening_hours_regular"),
            ("景区的营业时间是啥样的？", "opening_hours_regular"),
            ("公共交通怎么过来最方便？", "transport_metro_arrival"),
            ("坐什么车能到陈家祠？", "transport_metro_arrival"),
        )
        for text, expected_card in cases:
            with self.subTest(text=text):
                result = classify_visitor_qa_intent(text)
                self.assertEqual(result.name, "fact_card")
                self.assertEqual(result.fact_card_ids, (expected_card,))

    def test_photo_rules_do_not_collide_with_photo_spot_requests(self):
        rule = classify_visitor_qa_intent("园区里可以拍照吗？")
        spot = classify_visitor_qa_intent("馆里哪里拍照好看？")
        self.assertEqual(rule.name, "fact_card")
        self.assertEqual(rule.fact_card_ids, ("visit_service_photo_rule",))
        self.assertEqual(spot.name, "photo_spot")
        self.assertEqual(spot.fact_card_ids, ())

    def test_invoice_after_sale_question_stays_with_existing_controlled_flow(self):
        result = classify_visitor_qa_intent("发票开了还能退票吗？")
        self.assertEqual(result.name, "other")

    def test_nearby_food_and_attraction_paraphrases_have_distinct_intents(self):
        self.assertEqual(classify_visitor_qa_intent("附近有喝早茶的地方吗？").name, "nearby_food")
        self.assertEqual(classify_visitor_qa_intent("周边还有什么可以逛的地方？").name, "nearby_attraction")


if __name__ == "__main__":
    unittest.main()
