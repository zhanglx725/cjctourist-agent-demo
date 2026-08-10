from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from route_planner import plan_template
from state_transition_adapter import dry_run_transition
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


class StateTransitionShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tour = start_tour(plan_template("highlights_30"))
        self.interaction = initialize_interaction(self.tour)
        self.shadow_env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "state_transition",
        }

    def test_pure_preflight_never_calls_legacy_handler(self) -> None:
        with patch("tour_interaction.handle_tour_event", side_effect=AssertionError("must not execute")):
            result = dry_run_transition(
                "arrive_at_stop", self.tour, self.interaction,
                node_id="stop_front_courtyard_center",
            )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["expected_phase"], "explaining")
        self.assertEqual(result["reason_code"], "arrived")
        self.assertEqual(self.tour["visited_stop_ids"], [])

    def test_legacy_handler_invokes_the_shared_preflight_once(self) -> None:
        from tour_interaction import validate_tour_event_transition

        with patch("tour_interaction.validate_tour_event_transition", wraps=validate_tour_event_transition) as preflight:
            result = handle_tour_event(
                self.tour, self.interaction, "arrive_at_stop",
                node_id="stop_front_courtyard_center",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(preflight.call_count, 1)

    def test_common_event_preflights_match_legacy_contract(self) -> None:
        arrived = handle_tour_event(self.tour, self.interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        cases = (
            (self.tour, self.interaction, "arrive_at_stop", {"node_id": "stop_front_courtyard_center"}, "arrived"),
            (arrived["tour_state"], arrived["interaction_state"], "explanation_finished", {}, "explanation_finished"),
            (arrived["tour_state"], arrived["interaction_state"], "confirm_stop_complete", {}, "stop_completed"),
            (arrived["tour_state"], arrived["interaction_state"], "skip_stop", {}, "skipped"),
            (self.tour, self.interaction, "next_stop", {}, "next_stop_ready"),
            (self.tour, self.interaction, "finish_tour", {}, "tour_finished"),
        )
        for tour, interaction, event, payload, code in cases:
            with self.subTest(event=event):
                shadow = dry_run_transition(event, tour, interaction, **payload)
                legacy = handle_tour_event(tour, interaction, event, **payload)
                self.assertEqual(shadow["accepted"], legacy["ok"])
                self.assertEqual(shadow["reason_code"], legacy["code"])

    def test_rejections_match_without_state_changes(self) -> None:
        for event, payload, code in (
            ("arrive_at_stop", {"node_id": "unreviewed"}, "invalid_node_id"),
            ("explanation_finished", {}, "not_current_stop"),
            ("confirm_stop_complete", {}, "not_current_stop"),
        ):
            with self.subTest(event=event):
                shadow = dry_run_transition(event, self.tour, self.interaction, **payload)
                legacy = handle_tour_event(self.tour, self.interaction, event, **payload)
                self.assertFalse(shadow["accepted"])
                self.assertEqual(shadow["reason_code"], code)
                self.assertEqual(legacy["tour_state"], self.tour)
                self.assertEqual(legacy["interaction_state"], self.interaction)

    def test_graph_shadow_records_one_preflight_and_one_legacy_execution(self) -> None:
        state = {
            "messages": [HumanMessage(content="我到前院中部了。")],
            "tour_state": self.tour,
            "tour_interaction_state": self.interaction,
        }
        original = agent_graph.handle_tour_event
        with patch.dict(os.environ, self.shadow_env, clear=False), patch("agent_graph.handle_tour_event", wraps=original) as legacy:
            updates = agent_graph.tour_event_node(state, {"configurable": {"thread_id": "shadow-thread-a"}})
        self.assertEqual(legacy.call_count, 1)
        audit = updates["state_transition_evaluations"][-1]
        self.assertEqual(audit["thread_id"], "shadow-thread-a")
        self.assertEqual(audit["event_type"], "arrive_at_stop")
        self.assertEqual(audit["shadow_validation_status"], "accepted")
        self.assertTrue(audit["legacy_result_matches_shadow"])
        self.assertEqual(updates["tour_state"]["visited_stop_ids"], [])

    def test_shadow_off_writes_no_audit(self) -> None:
        state = {
            "messages": [HumanMessage(content="我到前院中部了。")],
            "tour_state": self.tour,
            "tour_interaction_state": self.interaction,
        }
        with patch.dict(os.environ, {"CJC_READ_ONLY_ROLLOUT_MODE": "off"}, clear=False):
            updates = agent_graph.tour_event_node(state)
        self.assertNotIn("state_transition_evaluations", updates)

    def test_shadow_capability_mismatch_is_audited_not_silent(self) -> None:
        state = {
            "messages": [HumanMessage(content="我到前院中部了。")],
            "tour_state": self.tour,
            "tour_interaction_state": self.interaction,
        }
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "atomic_read_plan",
        }, clear=False):
            updates = agent_graph.tour_event_node(state, {})
        audit = updates["state_transition_evaluations"][-1]
        self.assertEqual(audit["shadow_reason_code"], "capability_not_enabled")
        self.assertFalse(audit["legacy_result_matches_shadow"])
        self.assertEqual(audit["runtime_capabilities"], ["atomic_read_plan"])


if __name__ == "__main__":
    unittest.main()
