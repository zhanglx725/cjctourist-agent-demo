"""A1-1 contract tests for the sole deterministic interaction adapter."""

import unittest

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


class TourInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_template("highlights_30")

    def setUp(self):
        self.tour = start_tour(self.plan)
        self.interaction = initialize_interaction(self.tour)

    def _arrive_first(self):
        return handle_tour_event(
            self.tour, self.interaction, "arrive_at_stop", node_id="stop_front_courtyard_center"
        )

    def test_initialization_waits_for_first_formal_stop(self):
        self.assertEqual(self.interaction["pending_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(self.interaction["tour_mode"], "chat")
        self.assertEqual(self.interaction["stop_phase"], "navigating")

    def test_planned_arrival_does_not_mark_visit_until_confirmation(self):
        arrived = self._arrive_first()
        self.assertTrue(arrived["ok"])
        self.assertEqual(arrived["code"], "arrived")
        self.assertEqual(arrived["tour_state"]["current_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(arrived["tour_state"]["visited_stop_ids"], [])
        self.assertIn("stop_front_courtyard_center", arrived["tour_state"]["remaining_stop_ids"])
        self.assertEqual(arrived["interaction_state"]["stop_phase"], "explaining")

    def test_confirm_completion_is_the_only_transition_to_visited(self):
        arrived = self._arrive_first()
        completed = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )
        self.assertEqual(completed["code"], "stop_completed")
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])
        self.assertNotIn("stop_front_courtyard_center", completed["tour_state"]["remaining_stop_ids"])
        self.assertEqual(completed["interaction_state"]["pending_stop_id"], "label_moon_platform")
        self.assertEqual(completed["interaction_state"]["stop_phase"], "navigating")

    def test_repeated_arrival_and_completion_are_idempotent(self):
        arrived = self._arrive_first()
        repeated_arrival = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        self.assertTrue(repeated_arrival["idempotent"])
        completed = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )
        repeated_completion = handle_tour_event(
            completed["tour_state"], completed["interaction_state"], "confirm_stop_complete"
        )
        self.assertEqual(repeated_completion["code"], "already_completed")
        self.assertTrue(repeated_completion["idempotent"])
        self.assertEqual(repeated_completion["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])

    def test_self_arrival_preserves_formal_route_order_and_counts(self):
        result = handle_tour_event(
            self.tour, self.interaction, "arrive_at_stop", node_id="label_first_main_hall"
        )
        self.assertEqual(result["code"], "self_arrival")
        self.assertEqual(result["tour_state"]["current_stop_id"], "label_first_main_hall")
        self.assertEqual(result["tour_state"]["last_arrival_kind"], "self_arrival")
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_state"]["skipped_stop_ids"], [])
        self.assertEqual(result["tour_state"]["remaining_stop_ids"], self.tour["remaining_stop_ids"])
        self.assertEqual(result["interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(result["interaction_state"]["stop_phase"], "navigating")

    def test_unknown_node_returns_structured_rejection_without_mutation(self):
        result = handle_tour_event(self.tour, self.interaction, "arrive_at_stop", node_id="not_reviewed")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "invalid_node_id")
        self.assertEqual(result["tour_state"], self.tour)
        self.assertEqual(result["interaction_state"], self.interaction)

    def test_next_stop_cannot_bypass_current_confirmation(self):
        arrived = self._arrive_first()
        result = handle_tour_event(arrived["tour_state"], arrived["interaction_state"], "next_stop")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "invalid_phase")
        self.assertEqual(result["tour_state"]["remaining_stop_ids"][0], "stop_front_courtyard_center")

    def test_skip_current_stop_only_records_skip(self):
        arrived = self._arrive_first()
        result = handle_tour_event(arrived["tour_state"], arrived["interaction_state"], "skip_stop")
        self.assertEqual(result["code"], "skipped")
        self.assertIn("stop_front_courtyard_center", result["tour_state"]["skipped_stop_ids"])
        self.assertNotIn("stop_front_courtyard_center", result["tour_state"]["visited_stop_ids"])

    def test_detail_placeholder_does_not_change_tour_state(self):
        arrived = self._arrive_first()
        result = handle_tour_event(arrived["tour_state"], arrived["interaction_state"], "request_stop_detail")
        self.assertEqual(result["code"], "detail_placeholder")
        self.assertEqual(result["tour_state"], arrived["tour_state"])
        self.assertEqual(result["interaction_state"], arrived["interaction_state"])

    def test_finished_tour_rejects_non_finish_events_and_finish_is_idempotent(self):
        finished = handle_tour_event(self.tour, self.interaction, "finish_tour")
        rejected = handle_tour_event(
            finished["tour_state"], finished["interaction_state"], "next_stop"
        )
        self.assertEqual(rejected["code"], "tour_finished")
        repeated = handle_tour_event(
            finished["tour_state"], finished["interaction_state"], "finish_tour"
        )
        self.assertEqual(repeated["code"], "tour_already_finished")
        self.assertTrue(repeated["idempotent"])


if __name__ == "__main__":
    unittest.main()
