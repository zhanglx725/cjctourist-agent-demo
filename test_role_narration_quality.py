from __future__ import annotations

import unittest

from narration_style_policy import approved_style_ids
from role_narration_quality import (
    RoleNarrationQualityThresholds,
    evaluate_role_narration_shadow,
)


def accepted_record(style_id: str) -> dict:
    return {
        "style_id": style_id,
        "validation_status": "accepted",
        "reason_codes": [],
        "active_takeover": False,
        "fallback_used": False,
        "state_writes": [],
        "legacy_message_preserved": True,
    }


class RoleNarrationQualityTests(unittest.TestCase):
    def test_complete_approved_catalog_has_eighteen_styles(self):
        self.assertEqual(len(approved_style_ids()), 18)
        self.assertIn("listen_only", approved_style_ids())
        self.assertIn("cantonese_storyteller", approved_style_ids())

    def test_all_styles_require_evidence_before_active(self):
        report = evaluate_role_narration_shadow([])
        self.assertFalse(report["active_eligible"])
        self.assertEqual(report["evaluated_style_count"], 0)
        self.assertEqual(len(report["styles"]), 18)
        self.assertIn("insufficient_samples:neutral", report["blockers"])

    def test_clean_complete_batch_is_eligible_for_limited_active(self):
        records = [
            accepted_record(style_id)
            for style_id in approved_style_ids()
            for _ in range(3)
        ]
        report = evaluate_role_narration_shadow(records)
        self.assertTrue(report["active_eligible"])
        self.assertEqual(report["decision"], "eligible_for_limited_active")
        self.assertEqual(report["sample_count"], 54)

    def test_any_safety_or_state_violation_blocks_active(self):
        records = [
            accepted_record(style_id)
            for style_id in approved_style_ids()
            for _ in range(3)
        ]
        records[0] = {
            **records[0],
            "validation_status": "rejected",
            "reason_codes": ["internal_field_leak"],
            "state_writes": ["tour_state"],
        }
        report = evaluate_role_narration_shadow(
            records,
            thresholds=RoleNarrationQualityThresholds(min_acceptance_rate=0.0),
        )
        self.assertFalse(report["active_eligible"])
        self.assertIn("safety_violation_count:neutral", report["blockers"])
        self.assertIn("state_write_violation_count:neutral", report["blockers"])

    def test_listen_only_violation_is_a_hard_blocker(self):
        records = [accepted_record("listen_only") for _ in range(3)]
        records[0] = {
            **records[0], "validation_status": "rejected",
            "reason_codes": ["listen_only_interaction_violation"],
        }
        limits = RoleNarrationQualityThresholds(
            min_samples_per_style=0, min_acceptance_rate=0.0,
            min_schema_success_rate=0.0, max_fallback_rate=1.0,
        )
        report = evaluate_role_narration_shadow(records, thresholds=limits)
        self.assertFalse(report["active_eligible"])
        self.assertIn("safety_violation_count:listen_only", report["blockers"])

    def test_unknown_and_malformed_records_fail_closed(self):
        limits = RoleNarrationQualityThresholds(
            min_samples_per_style=0, min_acceptance_rate=0.0,
            min_schema_success_rate=0.0, max_fallback_rate=1.0,
        )
        report = evaluate_role_narration_shadow(
            [{"style_id": "invented"}, {"validation_status": "accepted"}],
            thresholds=limits,
        )
        self.assertFalse(report["active_eligible"])
        self.assertEqual(report["unknown_style_count"], 1)
        self.assertEqual(report["malformed_record_count"], 1)


if __name__ == "__main__":
    unittest.main()
