"""Tests for limited deterministic replanning under A1 completion semantics."""

import unittest

from replanning import replan_after_skip, replan_remaining_time
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


class ReplanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def _arrived_first_stop(self):
        tour = start_tour(self.plan)
        interaction = initialize_interaction(tour)
        return handle_tour_event(tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")

    def test_skip_current_unconfirmed_stop_never_marks_it_visited(self):
        arrived = self._arrived_first_stop()
        result = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "skip_stop"
        )
        self.assertIn("stop_front_courtyard_center", result["tour_state"]["skipped_stop_ids"])
        self.assertNotIn("stop_front_courtyard_center", result["tour_state"]["visited_stop_ids"])
        self.assertEqual(result["interaction_state"]["pending_stop_id"], "label_moon_platform")

    def test_short_time_preserves_current_unconfirmed_stop_once(self):
        arrived = self._arrived_first_stop()
        result = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "replan_time", available_minutes=20
        )
        state = result["tour_state"]
        self.assertEqual(state["remaining_stop_ids"].count("stop_front_courtyard_center"), 1)
        self.assertEqual(result["interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(result["interaction_state"]["stop_phase"], "explaining")
        self.assertNotIn("stop_front_courtyard_center", result["data"]["plan"].stop_ids)

    def test_empty_current_position_falls_back_to_entrance(self):
        result = replan_remaining_time(start_tour(self.plan), 20)
        self.assertEqual(result.plan.start_node_id, "entrance_main_outside")
        self.assertNotIn("entrance_main_outside", result.plan.stop_ids)

    def test_replan_never_readds_confirmed_stop(self):
        arrived = self._arrived_first_stop()
        completed = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )
        result = replan_remaining_time(completed["tour_state"], 20)
        self.assertNotIn("stop_front_courtyard_center", result.plan.stop_ids)
        self.assertEqual(result.tour_state["visited_stop_ids"], ["stop_front_courtyard_center"])

    def test_direct_skip_helper_still_uses_reviewed_graph(self):
        result = replan_after_skip(start_tour(self.plan))
        self.assertNotIn("stop_front_courtyard_center", result.plan.stop_ids)
        self.assertEqual(result.plan.full_path_node_ids[-1], "stop_front_courtyard_center")


if __name__ == "__main__":
    unittest.main()
