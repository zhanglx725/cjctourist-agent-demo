"""No-network tests for the pure A1-3 visitor response and action protocol."""

import unittest
from copy import deepcopy

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_presenter import present_clarification, present_tour_event, present_tour_state
from tour_state import start_tour


class TourPresenterTests(unittest.TestCase):
    def setUp(self):
        self.tour = start_tour(plan_template("highlights_30"))
        self.interaction = initialize_interaction(self.tour)

    @staticmethod
    def action_ids(view):
        return [action["id"] for action in view["actions"]]

    def arrive_first(self):
        return handle_tour_event(
            self.tour, self.interaction, "arrive_at_stop", node_id="stop_front_courtyard_center"
        )

    def test_navigating_view_exposes_stable_event_ids_and_pending_arguments(self):
        view = present_tour_state(self.tour, self.interaction)
        self.assertEqual(view["phase"], "navigating")
        self.assertIsNotNone(view["navigation"])
        self.assertIn("next_stop", self.action_ids(view))
        arrival = next(action for action in view["actions"] if action["id"] == "arrive_at_stop")
        self.assertEqual(arrival["arguments"], {"node_id": "stop_front_courtyard_center"})
        replan = next(action for action in view["actions"] if action["id"] == "replan_time")
        self.assertEqual(replan["input_schema"]["available_minutes"]["type"], "integer")

    def test_planned_arrival_view_enters_explaining_without_changing_snapshot(self):
        result = self.arrive_first()
        before_tour = deepcopy(result["tour_state"])
        before_interaction = deepcopy(result["interaction_state"])
        view = present_tour_event(result)
        self.assertEqual(view["phase"], "explaining")
        self.assertIn("explanation_finished", self.action_ids(view))
        self.assertIn("request_stop_detail", self.action_ids(view))
        self.assertEqual(result["tour_state"], before_tour)
        self.assertEqual(result["interaction_state"], before_interaction)

    def test_self_arrival_keeps_navigation_actions(self):
        result = handle_tour_event(
            self.tour, self.interaction, "arrive_at_stop", node_id="label_first_main_hall"
        )
        view = present_tour_event(result)
        self.assertEqual(view["phase"], "navigating")
        self.assertIsNotNone(view["navigation"])
        self.assertIn("next_stop", self.action_ids(view))
        self.assertIn("首进正厅", view["message"])
        self.assertIn("正式下一站", view["message"])

    def test_waiting_confirmation_exposes_confirm_not_explanation_finished(self):
        arrived = self.arrive_first()
        result = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "explanation_finished"
        )
        view = present_tour_event(result)
        self.assertEqual(view["phase"], "awaiting_confirmation")
        self.assertIn("confirm_stop_complete", self.action_ids(view))
        self.assertNotIn("explanation_finished", self.action_ids(view))

    def test_completion_skip_and_replan_return_navigating_actions(self):
        arrived = self.arrive_first()
        completed = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )
        self.assertEqual(present_tour_event(completed)["phase"], "navigating")
        skipped = handle_tour_event(
            self.tour, self.interaction, "skip_stop", node_id="stop_front_courtyard_center"
        )
        self.assertIn("arrive_at_stop", self.action_ids(present_tour_event(skipped)))
        replanned = handle_tour_event(self.tour, self.interaction, "replan_time", available_minutes=20)
        self.assertIn("next_stop", self.action_ids(present_tour_event(replanned)))

    def test_last_stop_completion_and_finish_have_no_actions(self):
        prepared_tour, prepared_interaction = self.tour, self.interaction
        for node_id in ["label_moon_platform", "stop_front_east_courtyard"]:
            skipped = handle_tour_event(
                prepared_tour, prepared_interaction, "skip_stop", node_id=node_id
            )
            prepared_tour, prepared_interaction = skipped["tour_state"], skipped["interaction_state"]
        arrived = handle_tour_event(
            prepared_tour, prepared_interaction, "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        explained = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "explanation_finished"
        )
        completed = handle_tour_event(
            explained["tour_state"], explained["interaction_state"], "confirm_stop_complete"
        )
        view = present_tour_event(completed)
        self.assertEqual(view["phase"], "finished")
        self.assertEqual(view["actions"], [])

    def test_error_and_clarification_have_no_actions(self):
        # Use an invalid reviewed-node request to obtain a structured error.
        error = handle_tour_event(self.tour, self.interaction, "arrive_at_stop", node_id="not_reviewed")
        error_view = present_tour_event(error)
        self.assertFalse(error_view["ok"])
        self.assertEqual(error_view["actions"], [])
        clarification = present_clarification("请说明具体点位。", self.interaction)
        self.assertEqual(clarification["code"], "clarification")
        self.assertEqual(clarification["actions"], [])


if __name__ == "__main__":
    unittest.main()
