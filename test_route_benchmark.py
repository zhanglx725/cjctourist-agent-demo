"""Regression tests for dynamic-versus-anchor route baselines."""

import unittest

from route_benchmark import run_benchmark_cases


class RouteBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {result.case_id: result for result in run_benchmark_cases()}

    def test_every_dynamic_route_is_within_its_allowed_budget(self):
        self.assertTrue(all(result.dynamic_within_budget for result in self.results.values()))

    def test_exact_anchor_duration_cases_fall_back_to_reviewed_routes_when_needed(self):
        for case_id in ("anchor_30_architecture", "anchor_60_crafts_stories", "anchor_90_deep_dive"):
            result = self.results[case_id]
            self.assertEqual(result.recommended_strategy, "anchor")
            self.assertIn("reviewed_anchor_fallback", result.reason_codes)
            self.assertTrue(result.anchor_within_budget)

    def test_non_anchor_durations_keep_dynamic_composition(self):
        for case_id in ("dynamic_45_plaster", "dynamic_75_crafts"):
            result = self.results[case_id]
            self.assertEqual(result.recommended_strategy, "dynamic")
            self.assertIsNone(result.anchor_route_id)

    def test_anchor_comparisons_expose_human_review_metrics(self):
        result = self.results["anchor_60_crafts_stories"]
        self.assertIsNotNone(result.anchor_stop_overlap)
        self.assertIsNotNone(result.anchor_key_stop_coverage)
        self.assertGreaterEqual(result.anchor_key_stop_coverage, 0)


if __name__ == "__main__":
    unittest.main()
