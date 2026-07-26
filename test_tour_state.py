"""Unit tests for TourState phase-A pure transitions."""

import unittest

from route_planner import plan_template
from tour_state import TourStateError, arrive_at_stop, finish_tour, next_stop, skip_stop, start_tour


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

    def test_arrival_updates_current_and_visit_once_then_next_is_moon_platform(self):
        state = start_tour(self.plan)
        arrived = arrive_at_stop(state, "stop_front_courtyard_center")
        repeated = arrive_at_stop(arrived, "stop_front_courtyard_center")
        self.assertEqual(repeated["current_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(repeated["visited_stop_ids"], ["stop_front_courtyard_center"])
        self.assertEqual(next_stop(repeated), "label_moon_platform")
        self.assertEqual(state["visited_stop_ids"], [])

    def test_skip_next_stop_changes_recommendation(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        skipped = skip_stop(state)
        self.assertEqual(skipped["skipped_stop_ids"], ["label_moon_platform"])
        self.assertEqual(next_stop(skipped), "stop_front_east_courtyard")
        self.assertFalse(set(skipped["visited_stop_ids"]).intersection(skipped["skipped_stop_ids"]))

    def test_all_processed_stops_complete_the_route(self):
        state = start_tour(self.plan)
        state = arrive_at_stop(state, "stop_front_courtyard_center")
        state = arrive_at_stop(state, "label_moon_platform")
        state = arrive_at_stop(state, "stop_front_east_courtyard")
        self.assertEqual(state["route_status"], "completed")
        self.assertEqual(state["remaining_stop_ids"], [])
        self.assertIsNone(next_stop(state))

    def test_unknown_marker_is_rejected(self):
        with self.assertRaises(TourStateError):
            arrive_at_stop(start_tour(self.plan), "not_a_real_node")

    def test_explicit_finish_preserves_actual_progress(self):
        state = arrive_at_stop(start_tour(self.plan), "stop_front_courtyard_center")
        finished = finish_tour(state)
        self.assertEqual(finished["route_status"], "completed")
        self.assertEqual(finished["completion_reason"], "visitor_finished_early")
        self.assertEqual(finished["visited_stop_ids"], ["stop_front_courtyard_center"])


if __name__ == "__main__":
    unittest.main()
