from __future__ import annotations

import unittest

from tools.build_role_narration_langsmith_fault_dataset import build_examples


class RoleNarrationLangSmithFaultDatasetTests(unittest.TestCase):
    def test_high_risk_fault_dataset_is_complete_and_fallback_only(self):
        examples = build_examples()
        self.assertEqual(len(examples), 12)
        self.assertEqual(
            {item["inputs"]["failure_type"] for item in examples},
            {"fact_drift", "style_forbidden", "interaction_violation", "model_failure", "budget_exceeded", "internal_leak"},
        )
        for item in examples:
            self.assertEqual(item["inputs"]["scene_kind"], "stop_guidance")
            self.assertFalse(item["outputs"]["expected_active_takeover"])
            self.assertTrue(item["outputs"]["expected_fallback_used"])
            self.assertEqual(item["outputs"]["expected_state_writes"], [])
            self.assertEqual(item["outputs"]["expected_coverage_commit_count"], 1)


if __name__ == "__main__":
    unittest.main()
