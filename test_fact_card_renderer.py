"""Tests for deterministic FactCard rendering and partial-answer behavior."""

from __future__ import annotations

import unittest

from fact_card_contract import FactCard
from fact_card_renderer import render_fact_cards


def _card(
    card_id: str,
    *,
    question_types: tuple[str, ...],
    template: str,
    dynamic: bool = False,
    enabled: bool = True,
) -> FactCard:
    return FactCard(
        card_id=card_id,
        domain="ticketing" if "ticketing" in template else "opening_hours",
        question_types=question_types,
        trigger_phrases=("示例问法",),
        fact_statements=(f"{card_id} 的公开事实。",),
        applicability_conditions=(),
        freshness_policy="dynamic" if dynamic else "static",
        freshness_notice="安排可能调整，请以当日公告为准。" if dynamic else None,
        public_template_id=template,
        partial_answer_policy="answer_confirmed_portion",
        source_refs=("S01",),
        runtime_status="enabled" if enabled else "disabled",
    )


class FactCardRendererTests(unittest.TestCase):
    def test_complete_answer_uses_only_card_fields_and_deduplicates_notice(self):
        answer = render_fact_cards((
            _card("opening_hours_regular", question_types=("time",), template="time_window", dynamic=True),
            _card("ticketing_refund", question_types=("rule",), template="ticketing_rule", dynamic=True),
        ), requested_question_types=("time", "rule"))
        self.assertEqual(answer.status, "complete")
        self.assertFalse(answer.partial)
        self.assertIn("开放与入馆", answer.message)
        self.assertIn("票务规则", answer.message)
        self.assertEqual(answer.message.count("安排可能调整"), 1)
        self.assertEqual(answer.unanswered_question_types, ())

    def test_partial_answer_keeps_confirmed_facts_and_names_uncovered_type(self):
        answer = render_fact_cards(
            (_card("ticketing_refund", question_types=("rule",), template="ticketing_rule"),),
            requested_question_types=("rule", "time"),
        )
        self.assertEqual(answer.status, "partial")
        self.assertTrue(answer.partial)
        self.assertEqual(answer.unanswered_question_types, ("time",))
        self.assertIn("ticketing_refund 的公开事实", answer.message)
        self.assertIn("能够确认的部分", answer.message)

    def test_disabled_cards_are_never_rendered(self):
        answer = render_fact_cards(
            (_card("opening_hours_regular", question_types=("time",), template="time_window", enabled=False),),
            requested_question_types=("time",),
        )
        self.assertEqual(answer.status, "no_matching_card")
        self.assertNotIn("opening_hours_regular", answer.message)

    def test_unknown_requested_type_is_rejected(self):
        with self.assertRaises(ValueError):
            render_fact_cards((), requested_question_types=("free_model_answer",))


if __name__ == "__main__":
    unittest.main()
