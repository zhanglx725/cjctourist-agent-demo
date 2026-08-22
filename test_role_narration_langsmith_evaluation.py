from __future__ import annotations

import unittest

from controlled_rollout import STOP_GUIDANCE_ACTIVE_STYLE_BATCHES
from tools.run_role_narration_langsmith_evaluation import summarize


def _record(style_id: str, *, fault: bool = False, quality: bool = True) -> dict:
    return {
        "style_id": style_id,
        "active_takeover": not fault,
        "fallback_used": fault,
        "commit_decision": "legacy_fallback_published" if fault else "role_candidate_published",
        "assertions": {"one": True, "two": True},
        "style_quality": (
            {"status": "scored", "role_fit": 2, "naturalness": 1, "distinctiveness": 2, "readability": 1}
            if quality else {"status": "unavailable"}
        ),
    }


class RoleNarrationLangSmithEvaluationTests(unittest.TestCase):
    def test_release_gate_requires_all_three_evidence_types(self):
        base = [_record(style) for batch in STOP_GUIDANCE_ACTIVE_STYLE_BATCHES for style in batch for _ in range(3)]
        faults = [_record("ancient_scholar", fault=True) for _ in range(12)]
        summary = summarize(base, faults)
        self.assertEqual([batch["case_count"] for batch in summary["batches"]], [21, 18, 15])
        self.assertTrue(summary["gates"]["release_eligible"])
        self.assertEqual(summary["quality"]["scored_case_count"], 54)

    def test_unscored_or_bad_fault_case_blocks_release(self):
        base = [_record(style, quality=False) for batch in STOP_GUIDANCE_ACTIVE_STYLE_BATCHES for style in batch for _ in range(3)]
        faults = [_record("ancient_scholar", fault=True) for _ in range(11)]
        faults.append({**_record("ancient_scholar", fault=True), "fallback_used": False})
        summary = summarize(base, faults)
        self.assertFalse(summary["gates"]["style_quality"])
        self.assertFalse(summary["gates"]["fault_fallback_12_of_12"])
        self.assertFalse(summary["gates"]["release_eligible"])

    def test_partial_batch_can_not_claim_full_matrix_release(self):
        base = [_record("neutral") for _ in range(3)]
        faults = [_record("ancient_scholar", fault=True) for _ in range(12)]
        summary = summarize(base, faults)
        self.assertFalse(summary["gates"]["base_matrix_complete_54_of_54"])
        self.assertFalse(summary["gates"]["deterministic_54_of_54"])
        self.assertFalse(summary["gates"]["release_eligible"])


if __name__ == "__main__":
    unittest.main()
