from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    cancel_replan_node,
    confirm_replan_and_next_node,
    confirm_replan_node,
    prepare_replan_candidate_node,
    show_replan_node,
)
from replanning import prepare_remaining_route_proposal, prepare_remaining_time_confirmation
from replan_composite_shadow import audit_replan_composite_operation
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


class ReplanCompositeShadowTests(unittest.TestCase):
    shadow_env = {
        "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
        "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "state_transition",
    }

    def _proposal_state(self) -> dict:
        tour = start_tour(plan_template("crafts_60"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="label_moon_platform"
        )
        self.assertTrue(arrived["ok"])
        confirmation = prepare_remaining_time_confirmation(
            arrived["tour_state"],
            origin_node_id="label_moon_platform",
            origin_source="confirmed_remaining_time",
        ).to_dict()
        proposal = prepare_remaining_route_proposal(
            arrived["tour_state"],
            origin_node_id="label_moon_platform",
            origin_source="confirmed_remaining_time",
            remaining_minutes=40,
        ).to_dict()
        return {
            "messages": [HumanMessage(content="确认使用新路线，然后前往下一站")],
            "tour_state": arrived["tour_state"],
            "tour_interaction_state": {
                **arrived["interaction_state"],
                "pending_action_kind": "replan_route_confirmation",
            },
            "pending_replan_proposal": proposal,
            "pending_replan_time_confirmation": None,
            "replan_composite_evaluations": [],
        }

    def test_pure_audit_never_calls_legacy_handler(self) -> None:
        with patch("tour_interaction.handle_tour_event", side_effect=AssertionError("must not execute")):
            audit = audit_replan_composite_operation(
                operation_kind="cancel_replan",
                legacy_event_sequence=[],
                tour_before={"selected_route_id": "old"},
                tour_after={"selected_route_id": "old"},
                interaction_before={}, interaction_after={},
                proposal_before={"status": "awaiting_route_confirmation"},
                proposal_after=None,
                time_confirmation_before=None, time_confirmation_after=None,
            )
        self.assertTrue(audit["matches_expected_contract"])

    def test_confirm_then_next_records_the_legal_two_event_sequence(self) -> None:
        state = self._proposal_state()
        with patch.dict(os.environ, self.shadow_env, clear=False):
            updates = confirm_replan_and_next_node(
                state, {"configurable": {"thread_id": "replan-composite-a"}}
            )
        audit = updates["replan_composite_evaluations"][-1]
        self.assertEqual(audit["thread_id"], "replan-composite-a")
        self.assertEqual(
            audit["legacy_event_sequence"],
            ["apply_replan_proposal", "next_stop"],
        )
        self.assertTrue(audit["matches_expected_contract"])
        self.assertIsNone(updates["pending_replan_proposal"])

    def test_confirm_records_one_apply_and_cancel_does_not_change_formal_route(self) -> None:
        state = self._proposal_state()
        with patch.dict(os.environ, self.shadow_env, clear=False):
            applied = confirm_replan_node(
                state, {"configurable": {"thread_id": "replan-composite-b"}}
            )
            cancelled = cancel_replan_node(
                state, {"configurable": {"thread_id": "replan-composite-c"}}
            )
        self.assertEqual(
            applied["replan_composite_evaluations"][-1]["legacy_event_sequence"],
            ["apply_replan_proposal"],
        )
        audit = cancelled["replan_composite_evaluations"][-1]
        self.assertEqual(audit["operation_kind"], "cancel_replan")
        self.assertTrue(audit["matches_expected_contract"])
        self.assertEqual(cancelled["tour_interaction_state"]["pending_action_kind"], None)
        self.assertEqual(cancelled.get("tour_state", state["tour_state"]), state["tour_state"])

    def test_candidate_preparation_is_audit_only_and_thread_local(self) -> None:
        state = self._proposal_state()
        confirmation = prepare_remaining_time_confirmation(
            state["tour_state"], origin_node_id="label_moon_platform",
            origin_source="confirmed_remaining_time",
        ).to_dict()
        candidate_state = {
            **state,
            "messages": [HumanMessage(content="40分钟")],
            "pending_replan_proposal": None,
            "pending_replan_time_confirmation": confirmation,
        }
        with patch.dict(os.environ, self.shadow_env, clear=False):
            updates = prepare_replan_candidate_node(
                candidate_state, {"configurable": {"thread_id": "replan-composite-d"}}
            )
        audit = updates["replan_composite_evaluations"][-1]
        self.assertEqual(audit["operation_kind"], "prepare_replan_candidate")
        self.assertTrue(audit["matches_expected_contract"])
        self.assertEqual(audit["thread_id"], "replan-composite-d")
        self.assertEqual(updates["tour_state"], state["tour_state"])

    def test_confirm_without_pending_proposal_is_audited_as_a_safe_noop(self) -> None:
        state = self._proposal_state()
        state["pending_replan_proposal"] = None
        state["messages"] = [HumanMessage(content="确认使用新路线")]
        before = state["tour_state"]
        with patch.dict(os.environ, self.shadow_env, clear=False):
            updates = show_replan_node(
                state, {"configurable": {"thread_id": "replan-composite-e"}}
            )
        audit = updates["replan_composite_evaluations"][-1]
        self.assertEqual(audit["operation_kind"], "confirm_replan_without_pending")
        self.assertTrue(audit["matches_expected_contract"])
        self.assertEqual(before, state["tour_state"])


if __name__ == "__main__":
    unittest.main()
