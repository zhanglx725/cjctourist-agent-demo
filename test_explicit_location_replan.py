"""P1-11 controlled replan previews from an explicit current location."""

import unittest
from copy import deepcopy

from replanning import prepare_remaining_route_proposal
from route_planner import plan_template
from tour_intent import classify_tour_intent
from tour_interaction import handle_tour_event, initialize_interaction
from tour_navigation import next_stop_navigation
from tour_presenter import present_replan_proposal
from tour_state import start_tour


ORIGIN = "stop_rear_courtyard_west"
FIRST = "stop_front_courtyard_center"


class ExplicitLocationReplanTests(unittest.TestCase):
    def setUp(self):
        tour = start_tour(plan_template("crafts_60"), interests=["灰塑", "木雕"])
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(tour, interaction, "arrive_at_stop", node_id=FIRST)
        completed = handle_tour_event(
            arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete"
        )
        self.tour = completed["tour_state"]
        self.interaction = completed["interaction_state"]

    def _relocated(self):
        arrival = handle_tour_event(self.tour, self.interaction, "arrive_at_stop", node_id=ORIGIN)
        self.assertEqual(arrival["code"], "self_arrival")
        # Pure proposal tests call the A1 adapter directly, so model the
        # route-confirmation phase that the Agent establishes after preview.
        return arrival["tour_state"], {
            **arrival["interaction_state"],
            "pending_action_kind": "replan_route_confirmation",
        }

    def test_controlled_composite_resolves_reviewed_origin(self):
        decision = classify_tour_intent(
            "我已经到后庭西侧了，在这个点重新安排后续行程。", self.tour, self.interaction
        )
        self.assertEqual(decision.route_kind, "replan_request")
        self.assertEqual(decision.arguments["node_id"], ORIGIN)
        self.assertTrue(decision.arguments["record_arrival"])

    def test_preview_preserves_formal_route_and_hides_old_pending(self):
        relocated, interaction = self._relocated()
        old_tour = deepcopy(relocated)
        old_interaction = deepcopy(interaction)
        proposal = prepare_remaining_route_proposal(
            relocated, origin_node_id=ORIGIN, origin_source="explicit_reviewed_arrival"
        ).to_dict()
        self.assertEqual(proposal["origin_node_id"], ORIGIN)
        self.assertNotIn(FIRST, proposal["stop_ids"])
        self.assertEqual(relocated, old_tour)
        self.assertEqual(interaction, old_interaction)
        view = present_replan_proposal(proposal)
        self.assertEqual(view["phase"], "replan_route_confirmation")
        self.assertNotIn("下一站", view["message"])
        self.assertNotIn(old_interaction["pending_stop_id"], view["message"])

    def test_confirm_applies_fresh_candidate_and_preserves_history(self):
        relocated, interaction = self._relocated()
        proposal = prepare_remaining_route_proposal(
            relocated, origin_node_id=ORIGIN, origin_source="explicit_reviewed_arrival"
        ).to_dict()
        applied = handle_tour_event(relocated, interaction, "apply_replan_proposal", proposal=proposal)
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["code"], "replan_proposal_applied")
        self.assertEqual(applied["tour_state"]["current_stop_id"], ORIGIN)
        self.assertIn(FIRST, applied["tour_state"]["visited_stop_ids"])
        self.assertEqual(applied["interaction_state"]["pending_stop_id"], proposal["stop_ids"][0])
        self.assertEqual(applied["tour_state"]["route_stop_ids"], [*applied["tour_state"]["visited_stop_ids"], *applied["tour_state"]["skipped_stop_ids"], *proposal["stop_ids"]])
        navigation = next_stop_navigation(applied["tour_state"])
        self.assertEqual(navigation.from_node_id, ORIGIN)

    def test_old_proposal_cannot_apply_after_another_arrival(self):
        relocated, interaction = self._relocated()
        proposal = prepare_remaining_route_proposal(
            relocated, origin_node_id=ORIGIN, origin_source="explicit_reviewed_arrival"
        ).to_dict()
        moved = handle_tour_event(relocated, interaction, "arrive_at_stop", node_id="label_moon_platform")
        rejected = handle_tour_event(
            moved["tour_state"], moved["interaction_state"], "apply_replan_proposal", proposal=proposal
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["code"], "stale_replan_proposal")

    def test_arrival_only_and_missing_origin_do_not_prepare_replan(self):
        arrival = classify_tour_intent("我到后庭西侧了。", self.tour, self.interaction)
        self.assertEqual(arrival.event_type, "arrive_at_stop")
        missing = classify_tour_intent("重新安排后面的路线。", self.tour, self.interaction)
        self.assertEqual(missing.route_kind, "replan_request")
        self.assertEqual(missing.arguments["node_id"], self.tour["current_stop_id"])
        no_current = start_tour(plan_template("highlights_30"))
        unresolved = classify_tour_intent("重新安排后面的路线。", no_current, initialize_interaction(no_current))
        self.assertEqual(unresolved.route_kind, "clarification")
        self.assertEqual(unresolved.reason_code, "replan_origin_unresolved")

    def test_explicit_location_without_active_route_fails_closed(self):
        decision = classify_tour_intent("我在后庭西侧，从这里规划路线。")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "initial_route_origin_not_supported")

    def test_replan_composed_with_completion_or_question_still_clarifies(self):
        for text in (
            "我到后庭西侧了，看完了，在这里重新安排后续行程。",
            "我到后庭西侧了，在这里重新安排后续行程，顺便讲讲这里。",
        ):
            with self.subTest(text=text):
                decision = classify_tour_intent(text, self.tour, self.interaction)
                self.assertEqual(decision.route_kind, "clarification")
                self.assertEqual(decision.reason_code, "multiple_intents")


if __name__ == "__main__":
    unittest.main()
