"""Contract tests for the high-frequency visitor FactCard migration boundary."""

from __future__ import annotations

import unittest

from fact_card_contract import FactCard, FactCardCatalog, FactCardValidationError


def _opening_hours_card(*, card_id: str = "opening_hours_regular") -> FactCard:
    return FactCard(
        card_id=card_id,
        domain="opening_hours",
        question_types=("time", "availability"),
        trigger_phrases=("营业时间", "几点开门", "几点关门"),
        fact_statements=("常规开放安排以馆方当日公告为准。",),
        applicability_conditions=("不适用于馆方临时闭馆或特别公告。",),
        freshness_policy="dynamic",
        freshness_notice="开放安排可能调整，请以馆方当日公告为准。",
        public_template_id="time_window",
        partial_answer_policy="answer_confirmed_portion",
        source_refs=("S03",),
        limitations=("不承诺未来日期的临时安排。",),
    )


class FactCardContractTests(unittest.TestCase):
    def test_dynamic_card_round_trips_with_all_public_rendering_fields(self):
        card = _opening_hours_card()
        restored = FactCard.from_dict(card.to_dict())
        self.assertEqual(restored, card)
        self.assertEqual(restored.public_template_id, "time_window")
        self.assertEqual(restored.partial_answer_policy, "answer_confirmed_portion")
        self.assertEqual(restored.source_refs, ("S03",))

    def test_dynamic_card_requires_freshness_notice(self):
        with self.assertRaises(FactCardValidationError):
            FactCard(
                **{**_opening_hours_card().to_dict(), "freshness_notice": ""}
            )

    def test_fact_statements_cannot_contain_internal_retrieval_text(self):
        value = _opening_hours_card().to_dict()
        value["fact_statements"] = ["详见 03_visit_services.md（来源 S03）。"]
        with self.assertRaises(FactCardValidationError):
            FactCard(**value)

    def test_only_reviewed_official_ticketing_url_is_allowed_in_public_facts(self):
        value = _opening_hours_card().to_dict()
        value["fact_statements"] = ["购票入口：https://wx.gzcjc.com.cn。"]
        self.assertIsInstance(FactCard(**value), FactCard)
        value["fact_statements"] = ["购票入口：https://example.invalid。"]
        with self.assertRaises(FactCardValidationError):
            FactCard(**value)

    def test_unknown_or_extra_serialized_fields_fail_closed(self):
        serialized = _opening_hours_card().to_dict()
        serialized["unreviewed_free_text"] = "not allowed"
        self.assertIsNone(FactCard.from_dict(serialized))
        serialized = _opening_hours_card().to_dict()
        serialized["public_template_id"] = "free_model_answer"
        self.assertIsNone(FactCard.from_dict(serialized))

    def test_catalog_requires_unique_card_ids_and_strict_round_trip(self):
        transport = FactCard(
            card_id="transport_metro",
            domain="transport",
            question_types=("method", "location"),
            trigger_phrases=("怎么坐地铁", "公共交通"),
            fact_statements=("可结合陈家祠站的现场指引安排到达。",),
            applicability_conditions=(),
            freshness_policy="static",
            freshness_notice=None,
            public_template_id="transport_options",
            partial_answer_policy="clarify",
            source_refs=("S01",),
        )
        catalog = FactCardCatalog(cards=(_opening_hours_card(), transport))
        self.assertEqual(FactCardCatalog.from_dict(catalog.to_dict()), catalog)
        with self.assertRaises(FactCardValidationError):
            FactCardCatalog(cards=(_opening_hours_card(), _opening_hours_card()))


if __name__ == "__main__":
    unittest.main()
