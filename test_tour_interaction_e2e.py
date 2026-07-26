"""Offline end-to-end acceptance tests for the completed A1 tour loop.

These tests deliberately use deterministic route planning, text intent routing,
the single interaction adapter and the UI-neutral presenter.  They do not
invoke the real chat model, RAG, or any web frontend.
"""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import (
    clarification_node,
    direct_route_node,
    profile_update_node,
    route_initial_request,
    tour_event_node,
)
from tour_interaction import handle_tour_event


def _message_state(text: str, initial: dict | None = None) -> dict:
    """Make a minimal offline AgentState snapshot for one visitor message."""
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


def _merge(state: dict, update: dict) -> dict:
    """Model LangGraph's state update for the fields used in this test file."""
    return {**state, **update}


class TourInteractionE2ETests(unittest.TestCase):
    def _started(self) -> dict:
        return direct_route_node(_message_state("我有30分钟，帮我规划路线"))

    def _agent_event(self, state: dict, text: str) -> tuple[dict, dict]:
        request = _message_state(text, state)
        self.assertEqual(route_initial_request(request), "tour_event")
        update = tour_event_node(request)
        return _merge(state, update), update

    def _arrive_and_finish_explanation(self, state: dict) -> dict:
        state, _ = self._agent_event(state, "我到前院中部了")
        explained = handle_tour_event(
            state["tour_state"], state["tour_interaction_state"], "explanation_finished"
        )
        self.assertTrue(explained["ok"])
        return _merge(
            state,
            {
                "tour_state": explained["tour_state"],
                "tour_interaction_state": explained["interaction_state"],
            },
        )

    def _agent_profile_update(self, state: dict, text: str) -> tuple[dict, dict]:
        request = _message_state(text, state)
        self.assertEqual(route_initial_request(request), "profile_update")
        update = profile_update_node(request)
        return _merge(state, update), update

    def test_planned_stop_lifecycle_requires_confirm_before_next_stop(self):
        state = self._started()
        state = self._arrive_and_finish_explanation(state)
        self.assertEqual(state["tour_interaction_state"]["stop_phase"], "awaiting_confirmation")
        self.assertEqual(state["tour_state"]["visited_stop_ids"], [])

        state, update = self._agent_event(state, "讲完了，去下一站")
        self.assertEqual(update["last_tour_intent"]["event_type"], "confirm_stop_complete")
        self.assertEqual(state["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])
        self.assertEqual(state["tour_interaction_state"]["pending_stop_id"], "label_moon_platform")
        self.assertEqual(state["tour_presentation"]["phase"], "navigating")
        self.assertIn("arrive_at_stop", [item["id"] for item in state["tour_presentation"]["actions"]])

    def test_last_stop_never_auto_completes_before_explicit_confirmation(self):
        state = self._started()
        for node_id in ("label_moon_platform", "stop_front_east_courtyard"):
            skipped = handle_tour_event(
                state["tour_state"], state["tour_interaction_state"], "skip_stop", node_id=node_id
            )
            state = _merge(
                state,
                {"tour_state": skipped["tour_state"], "tour_interaction_state": skipped["interaction_state"]},
            )

        state = self._arrive_and_finish_explanation(state)
        self.assertNotEqual(state["tour_state"]["route_status"], "completed")
        state, _ = self._agent_event(state, "讲完了，去下一站")
        self.assertEqual(state["tour_state"]["route_status"], "completed")
        self.assertEqual(state["tour_interaction_state"]["stop_phase"], "finished")
        self.assertEqual(state["tour_presentation"]["actions"], [])

    def test_self_arrival_records_reality_then_keeps_formal_route(self):
        state = self._started()
        state, update = self._agent_event(state, "我到首进正厅了")
        self.assertEqual(update["last_tour_intent"]["event_type"], "arrive_at_stop")
        self.assertEqual(state["tour_presentation"]["code"], "self_arrival")
        self.assertEqual(state["tour_state"]["current_stop_id"], "label_first_main_hall")
        self.assertEqual(state["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(state["tour_interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")

        state, _ = self._agent_event(state, "下一站去哪？")
        self.assertEqual(state["tour_presentation"]["code"], "next_stop_ready")
        self.assertEqual(
            state["tour_presentation"]["navigation"].next_stop_id,
            "stop_front_courtyard_center",
        )

    def test_skip_then_remaining_time_replan_is_safe(self):
        state = self._started()
        state, _ = self._agent_event(state, "跳过前院中部")
        self.assertIn("stop_front_courtyard_center", state["tour_state"]["skipped_stop_ids"])
        self.assertNotIn("stop_front_courtyard_center", state["tour_state"]["visited_stop_ids"])

        state, update = self._agent_profile_update(state, "我只剩20分钟")
        self.assertEqual(update["last_profile_update"]["code"], "profile_replanned")
        self.assertEqual(state["tour_presentation"]["code"], "profile_replanned")
        self.assertEqual(state["tour_state"]["available_minutes"], 20)
        self.assertNotIn("stop_front_courtyard_center", state["tour_state"]["remaining_stop_ids"])
        self.assertNotIn("stop_front_courtyard_center", state["tour_state"]["visited_stop_ids"])

    def test_text_event_uses_intent_agent_adapter_and_presentation_in_order(self):
        state = self._started()
        request = _message_state("我到前院中部了", state)
        with patch("agent_graph.handle_tour_event", wraps=agent_graph.handle_tour_event) as adapter:
            update = tour_event_node(request)
        self.assertEqual(update["last_tour_intent"]["event_type"], "arrive_at_stop")
        adapter.assert_called_once_with(
            state["tour_state"], state["tour_interaction_state"], "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        self.assertEqual(update["tour_presentation"]["phase"], "explaining")
        self.assertIn("explanation_finished", [item["id"] for item in update["tour_presentation"]["actions"]])

    def test_ambiguous_multi_intent_and_unknown_node_have_no_partial_state_update(self):
        state = self._started()
        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        for text in (
            "我到月台和前庭之间了",
            "我到月台了，顺便讲讲月台石雕",
            "我到不存在展厅了",
        ):
            request = _message_state(text, state)
            self.assertEqual(route_initial_request(request), "clarification")
            update = clarification_node(request)
            self.assertNotIn("tour_state", update)
            self.assertNotIn("tour_interaction_state", update)
            self.assertEqual(update["tour_presentation"]["actions"], [])
            self.assertEqual(state["tour_state"], before_tour)
            self.assertEqual(state["tour_interaction_state"], before_interaction)

    def test_detail_request_and_repeated_events_are_side_effect_safe(self):
        state = self._started()
        state, _ = self._agent_event(state, "我到前院中部了")
        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        detail = handle_tour_event(
            state["tour_state"], state["tour_interaction_state"], "request_stop_detail"
        )
        self.assertEqual(detail["code"], "detail_requested")
        self.assertEqual(detail["tour_state"], before_tour)
        self.assertEqual(detail["interaction_state"], before_interaction)

        repeated_arrival = handle_tour_event(
            state["tour_state"], state["tour_interaction_state"], "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        explained = handle_tour_event(
            state["tour_state"], state["tour_interaction_state"], "explanation_finished"
        )
        repeated_explanation = handle_tour_event(
            explained["tour_state"], explained["interaction_state"], "explanation_finished"
        )
        completed = handle_tour_event(
            explained["tour_state"], explained["interaction_state"], "confirm_stop_complete"
        )
        repeated_completion = handle_tour_event(
            completed["tour_state"], completed["interaction_state"], "confirm_stop_complete"
        )
        self.assertTrue(repeated_arrival["idempotent"])
        self.assertTrue(repeated_explanation["idempotent"])
        self.assertTrue(repeated_completion["idempotent"])
        self.assertEqual(repeated_completion["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])


if __name__ == "__main__":
    unittest.main()
