"""Tests for TourState's first limited deterministic replanning policies."""

import unittest

from replanning import replan_after_skip, replan_remaining_time
from route_planner import plan_template
from tour_state import arrive_at_stop, start_tour


class ReplanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def test_skip_next_stop_removes_it_from_replanned_route(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        result = replan_after_skip(state)
        self.assertNotIn("label_moon_platform", result.plan.stop_ids)
        self.assertIn("label_moon_platform", result.tour_state["skipped_stop_ids"])
        self.assertEqual(result.plan.start_node_id, "stop_front_courtyard_center")
        self.assertEqual(result.plan.full_path_node_ids[-1], "stop_front_courtyard_center")

    def test_short_time_from_current_position_is_walkable_and_budgeted(self):
        state = arrive_at_stop(start_tour(self.plan), "label_moon_platform")
        result = replan_remaining_time(state, 20)
        self.assertNotIn("label_moon_platform", result.plan.stop_ids)
        self.assertTrue(result.plan.within_time_budget)
        self.assertLessEqual(result.plan.estimated_total_seconds, result.plan.allowed_total_seconds)
        self.assertEqual(result.plan.full_path_node_ids[0], "label_moon_platform")

    def test_empty_current_position_falls_back_to_entrance(self):
        result = replan_remaining_time(start_tour(self.plan), 20)
        self.assertEqual(result.plan.start_node_id, "entrance_main_outside")
        self.assertNotIn("entrance_main_outside", result.plan.stop_ids)

    def test_replan_never_readds_visited_stop(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        result = replan_remaining_time(state, 20)
        self.assertNotIn("stop_front_courtyard_center", result.plan.stop_ids)
        self.assertEqual(result.tour_state["visited_stop_ids"], ["stop_front_courtyard_center"])


if __name__ == "__main__":
    unittest.main()
