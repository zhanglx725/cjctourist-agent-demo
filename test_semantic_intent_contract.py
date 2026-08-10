from __future__ import annotations

import unittest

from intent_arbitration import arbitrate_intents
from semantic_intent_contract import build_intent_envelope


def candidate(intent: str, confidence: float, evidence: str, **arguments):
    return {
        "intent": intent,
        "confidence": confidence,
        "target": None,
        "arguments": arguments,
        "source": "model",
        "requires_confirmation": False,
        "evidence_span": evidence,
    }


class SemanticIntentContractTests(unittest.TestCase):
    def test_envelope_limits_sorts_deduplicates_and_rejects_node_fields(self):
        text = "我到前院了，再讲详细一点"
        values = [
            candidate("ask_follow_up_detail", 0.86, "详细一点", subject_text=""),
            candidate("arrive_at_stop", 0.95, "到前院", location_text="前院"),
            candidate("arrive_at_stop", 0.92, "到前院", location_text="前院"),
            {**candidate("finish_tour", 0.99, "到前院"), "node_id": "stop_guidance"},
        ]
        envelope = build_intent_envelope(text, values, model_called=True)
        self.assertEqual([x.intent for x in envelope.candidates], ["arrive_at_stop", "ask_follow_up_detail"])
        self.assertTrue(envelope.model_called)

    def test_state_intent_requires_higher_confidence_than_read_only(self):
        read = build_intent_envelope("详细讲讲", [candidate("ask_follow_up_detail", 0.81, "详细讲讲", subject_text="")])
        self.assertEqual(arbitrate_intents(read, {}).status, "accepted")
        write = build_intent_envelope("结束游览", [candidate("finish_tour", 0.89, "结束游览")])
        result = arbitrate_intents(write, {"tour_state": {"route_status": "touring"}})
        self.assertEqual(result.status, "clarification")

    def test_conflicting_state_intents_fail_closed(self):
        text = "完成本点但也跳过本点"
        envelope = build_intent_envelope(text, [
            candidate("confirm_stop_complete", 0.96, "完成本点"),
            candidate("skip_stop", 0.95, "跳过本点", stop_text="本点"),
        ])
        self.assertEqual(arbitrate_intents(envelope, {"tour_state": {"route_status": "touring"}}).reason_code, "conflicting_state_intents")

    def test_deterministic_route_always_wins(self):
        envelope = build_intent_envelope("结束游览", [candidate("finish_tour", 0.99, "结束游览")])
        result = arbitrate_intents(envelope, {}, deterministic_route_target="inactive_tour_end")
        self.assertEqual(result.route_target, "inactive_tour_end")
        self.assertEqual(result.reason_code, "deterministic_priority")

    def test_active_tour_guard_blocks_event_without_route(self):
        envelope = build_intent_envelope("我到前院了", [candidate("arrive_at_stop", 0.96, "我到前院了", location_text="前院")])
        result = arbitrate_intents(envelope, {})
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason_code, "intent_not_allowed_without_active_tour")

    def test_missing_required_argument_is_rejected_by_contract(self):
        envelope = build_intent_envelope(
            "我想用英文",
            [candidate("select_language", 0.99, "英文")],
        )
        self.assertEqual(envelope.candidates, ())


if __name__ == "__main__":
    unittest.main()
