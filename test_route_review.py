"""Tests for the A0-6 automatic checks and human-review handoff."""

import unittest

from route_review import build_review_records


class RouteReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = {record["case_id"]: record for record in build_review_records()}

    def test_every_benchmark_case_has_a_pending_manual_review(self):
        self.assertEqual(len(self.records), 5)
        self.assertTrue(all(record["manual_review"]["status"] == "pending" for record in self.records.values()))

    def test_automatic_checks_keep_route_constraints_visible(self):
        record = self.records["dynamic_45_plaster"]
        self.assertTrue(record["automatic_checks"]["all_guide_stops_are_reviewed_and_ornament_rich"])
        self.assertEqual(record["automatic_checks"]["repeated_guide_stop_ids"], [])
        self.assertTrue(record["automatic_checks"]["path_returns_to_front_courtyard_exit_area"])
        self.assertTrue(record["time_seconds"]["within_budget"])

    def test_anchor_case_keeps_the_selected_anchor_route_for_review(self):
        record = self.records["anchor_60_crafts_stories"]
        self.assertEqual(record["recommended_strategy"], "anchor")
        self.assertEqual(record["chosen_route_source"], "anchor:crafts_60")


if __name__ == "__main__":
    unittest.main()
