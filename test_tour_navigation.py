"""Tests for deterministic next-stop navigation over reviewed space edges."""

import unittest

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_navigation import format_next_stop_navigation, next_stop_navigation
from tour_state import start_tour


class TourNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def _complete_first_stop(self):
        tour = start_tour(self.plan)
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        return handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )

    def test_first_next_stop_starts_at_entrance_and_is_reachable(self):
        instruction = next_stop_navigation(start_tour(self.plan))
        self.assertIsNotNone(instruction)
        self.assertEqual(instruction.from_node_id, "entrance_main_outside")
        self.assertEqual(instruction.next_stop_id, "stop_front_courtyard_center")
        self.assertGreater(len(instruction.edge_ids), 0)
        self.assertIsNotNone(instruction.estimated_walk_seconds)

    def test_confirmation_advances_to_moon_platform_with_guide_focus(self):
        completed = self._complete_first_stop()
        instruction = next_stop_navigation(completed["tour_state"])
        self.assertEqual(instruction.next_stop_id, "label_moon_platform")
        self.assertIn("栏杆", instruction.guide_focus)
        self.assertIn("下一站", format_next_stop_navigation(instruction))

    def test_explicit_target_navigation_keeps_original_state_valid(self):
        state = start_tour(self.plan)
        instruction = next_stop_navigation(state, target_stop_id="label_moon_platform")
        self.assertEqual(instruction.next_stop_id, "label_moon_platform")
        self.assertEqual(state["remaining_stop_ids"][0], "stop_front_courtyard_center")

    def test_completed_route_has_no_next_stop_message(self):
        result = self._complete_first_stop()
        for node_id in ("label_moon_platform", "stop_front_east_courtyard"):
            arrived = handle_tour_event(result["tour_state"], result["interaction_state"], "arrive_at_stop", node_id=node_id)
            result = handle_tour_event(arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete")
        self.assertIsNone(next_stop_navigation(result["tour_state"]))
        self.assertIn("均已完成", format_next_stop_navigation(None))


if __name__ == "__main__":
    unittest.main()
