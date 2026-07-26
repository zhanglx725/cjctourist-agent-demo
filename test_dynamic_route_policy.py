"""Static contract tests for dynamic-route parameters."""

import json
import unittest
from pathlib import Path


POLICY_FILE = Path("data/chen_clan_academy/routes/dynamic_route_policy_v1.json")


class DynamicRoutePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))

    def test_duration_bounds_are_sensible(self):
        duration = self.policy["duration_policy"]
        self.assertEqual(duration["minimum_minutes"], 20)
        self.assertEqual(duration["maximum_minutes"], 120)
        self.assertGreater(duration["maximum_overrun_ratio"], 0)

    def test_anchor_routes_are_preserved(self):
        self.assertEqual(
            self.policy["duration_policy"]["anchor_template_minutes"], [30, 60, 90]
        )

    def test_candidates_require_approved_ornament_rich_stops(self):
        candidate = self.policy["candidate_policy"]
        self.assertEqual(candidate["required_review_status"], "approved")
        self.assertEqual(candidate["minimum_mapped_ornament_count"], 4)
        self.assertIn("core", candidate["allowed_route_roles"])
        self.assertIn("optional", candidate["allowed_route_roles"])

    def test_dynamic_stop_budget_reserves_the_full_visit_experience(self):
        budget = self.policy["experience_budget_per_stop_seconds"]
        self.assertGreater(budget["guide"], 0)
        self.assertGreater(budget["observation"], 0)
        self.assertGreater(budget["interaction"], 0)


if __name__ == "__main__":
    unittest.main()
