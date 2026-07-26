"""Tests for deterministic next-stop navigation over reviewed space edges."""

import unittest

from route_planner import plan_template
from tour_navigation import format_next_stop_navigation, next_stop_navigation
from tour_state import arrive_at_stop, skip_stop, start_tour


class TourNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def test_first_next_stop_starts_at_entrance_and_is_reachable(self):
        instruction = next_stop_navigation(start_tour(self.plan))
        self.assertIsNotNone(instruction)
        self.assertEqual(instruction.from_node_id, "entrance_main_outside")
        self.assertEqual(instruction.next_stop_id, "stop_front_courtyard_center")
        self.assertGreater(len(instruction.edge_ids), 0)
        self.assertIsNotNone(instruction.estimated_walk_seconds)

    def test_arrival_advances_to_moon_platform_with_guide_focus(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        instruction = next_stop_navigation(state)
        self.assertEqual(instruction.next_stop_id, "label_moon_platform")
        self.assertIn("栏杆", instruction.guide_focus)
        self.assertIn("下一站", format_next_stop_navigation(instruction))

    def test_skipped_stop_is_not_recommended_again(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        instruction = next_stop_navigation(skip_stop(state))
        self.assertEqual(instruction.next_stop_id, "stop_front_east_courtyard")

    def test_completed_route_has_no_next_stop_message(self):
        state = start_tour(self.plan)
        state = arrive_at_stop(state, "stop_front_courtyard_center")
        state = arrive_at_stop(state, "label_moon_platform")
        state = arrive_at_stop(state, "stop_front_east_courtyard")
        self.assertIsNone(next_stop_navigation(state))
        self.assertIn("均已完成", format_next_stop_navigation(None))


if __name__ == "__main__":
    unittest.main()
