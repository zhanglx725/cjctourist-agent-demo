"""Unit tests for TourState route facts, excluding A1 interaction events."""

import unittest

from route_planner import plan_template
from tour_state import finish_tour, next_stop, skip_stop, start_tour


class TourStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def test_start_tour_has_no_current_stop_and_keeps_formal_stops_only(self):
        state = start_tour(self.plan, interests=["建筑装饰"])
        self.assertIsNone(state["current_stop_id"])
        self.assertEqual(state["selected_route_id"], "highlights_30")
        self.assertEqual(
            state["remaining_stop_ids"],
            ["stop_front_courtyard_center", "label_moon_platform", "stop_front_east_courtyard"],
        )
        self.assertNotIn("entrance_main_outside", state["route_stop_ids"])

    def test_next_stop_reads_first_remaining_without_changing_state(self):
        state = start_tour(self.plan)
        self.assertEqual(next_stop(state), "stop_front_courtyard_center")
        self.assertEqual(state["visited_stop_ids"], [])
        self.assertEqual(len(state["remaining_stop_ids"]), 3)

    def test_skip_moves_only_remaining_stop_to_skipped(self):
        state = start_tour(self.plan)
        skipped = skip_stop(state)
        self.assertEqual(skipped["skipped_stop_ids"], ["stop_front_courtyard_center"])
        self.assertEqual(skipped["visited_stop_ids"], [])
        self.assertEqual(next_stop(skipped), "label_moon_platform")

    def test_skipping_all_stops_completes_route_without_false_visits(self):
        state = start_tour(self.plan)
        while state["remaining_stop_ids"]:
            state = skip_stop(state)
        self.assertEqual(state["route_status"], "completed")
        self.assertEqual(state["visited_stop_ids"], [])
        self.assertEqual(len(state["skipped_stop_ids"]), 3)

    def test_explicit_finish_preserves_actual_progress(self):
        finished = finish_tour(start_tour(self.plan))
        self.assertEqual(finished["route_status"], "completed")
        self.assertEqual(finished["completion_reason"], "visitor_finished_early")
        self.assertEqual(finished["visited_stop_ids"], [])


if __name__ == "__main__":
    unittest.main()
