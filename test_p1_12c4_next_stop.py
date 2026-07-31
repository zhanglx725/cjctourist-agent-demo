"""P1-12C4 tests for state-grounded next-stop control routing."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    confirm_replan_and_next_node,
    confirm_replan_node,
    direct_route_node,
    prepare_replan_candidate_node,
    route_initial_request,
    semantic_normalization_node,
    tour_event_node,
)
from semantic_normalization import SemanticCandidate, canonical_control_text, validate_candidate


def _turn(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class P112C4NextStopTests(unittest.TestCase):
    @staticmethod
    def _active_state() -> dict:
        return direct_route_node(_turn("我有30分钟，帮我规划路线。"))

    def _time_confirmation_state(self) -> tuple[dict, dict]:
        initial = self._active_state()
        arrival = _turn("我到后庭了。", initial)
        self.assertEqual(route_initial_request(arrival), "tour_event")
        confirmation = tour_event_node(arrival)
        return arrival, confirmation

    def _pending_route_confirmation_state(self) -> dict:
        arrival, confirmation = self._time_confirmation_state()
        time_state = _turn("我还有30分钟。", {**arrival, **confirmation})
        self.assertEqual(route_initial_request(time_state), "prepare_replan_candidate")
        candidate = prepare_replan_candidate_node(time_state)
        return {**time_state, **candidate}

    def test_common_next_stop_controls_are_deterministic_and_never_call_model(self):
        expressions = (
            "下一个", "下一处", "下一个点", "接下来去哪", "接着去哪",
            "往下走吧", "继续去后面一站", "带我去下一站",
            "咱们接着往后看吧", "下面该去哪儿了",
        )
        for text in expressions:
            with self.subTest(text=text):
                initial = self._active_state()
                state = _turn(text, initial)
                with patch("agent_graph.recognize_semantic_candidate") as recognizer:
                    state.update(semantic_normalization_node(state))
                recognizer.assert_not_called()
                self.assertFalse(state["performance_metrics"][-1]["model_called"])
                self.assertEqual(route_initial_request(state), "tour_event")
                result = tour_event_node(state)
                self.assertEqual(result["last_tour_event"]["code"], "next_stop_ready")
                self.assertEqual(result["tour_state"], initial["tour_state"])
                self.assertEqual(result["tour_interaction_state"], initial["tour_interaction_state"])

    def test_semantic_next_stop_candidate_is_closed_and_reuses_existing_event(self):
        text = "接下来带路"
        candidate = validate_candidate(text, {
            "candidate_type": "request_next_stop",
            "evidence_span": text,
            "confidence": 0.95,
        })
        self.assertTrue(candidate.actionable)
        self.assertEqual(canonical_control_text(candidate), "下一站怎么走")
        state = _turn(text, self._active_state())
        with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
            state.update(semantic_normalization_node(state))
        self.assertEqual(state["semantic_control_text"], "下一站怎么走")
        self.assertEqual(route_initial_request(state), "tour_event")
        self.assertEqual(tour_event_node(state)["last_tour_event"]["code"], "next_stop_ready")

    def test_unrecognized_control_shape_clarifies_without_llm_or_rag(self):
        state = _turn("往前走")
        with patch("agent_graph.recognize_semantic_candidate", return_value=SemanticCandidate()):
            state.update(semantic_normalization_node(state))
        self.assertEqual(route_initial_request(state), "clarification")
        self.assertNotIn("tour_state", state)
        self.assertEqual(state["performance_metrics"][-1]["model_called"], True)

    def test_no_route_next_stop_is_a_structured_adapter_refusal_not_rag(self):
        state = _turn("下一个")
        with patch("agent_graph.recognize_semantic_candidate") as recognizer:
            state.update(semantic_normalization_node(state))
        recognizer.assert_not_called()
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertFalse(result["last_tour_event"]["ok"])
        self.assertNotIn("tour_state", result)
        self.assertIn("先建立游览路线", result["messages"][0].content)

    def test_next_stop_is_blocked_during_both_replan_confirmation_phases(self):
        arrival, time_confirmation = self._time_confirmation_state()
        time_state = _turn("下一个", {**arrival, **time_confirmation})
        self.assertEqual(route_initial_request(time_state), "show_replan_time")
        self.assertEqual(time_state["tour_state"], time_confirmation["tour_state"])

        candidate_state = self._pending_route_confirmation_state()
        route_state = _turn("下一个", candidate_state)
        self.assertEqual(route_initial_request(route_state), "show_replan")
        self.assertEqual(route_state["tour_state"], candidate_state["tour_state"])
        self.assertEqual(route_state["pending_replan_proposal"], candidate_state["pending_replan_proposal"])

    def test_confirmed_replan_next_stop_reads_applied_route_and_current_position(self):
        candidate_state = self._pending_route_confirmation_state()
        original = deepcopy(candidate_state["tour_state"])
        applied = confirm_replan_node(_turn("确认新路线", candidate_state))
        applied_state = {**candidate_state, **applied}
        self.assertIsNone(applied_state["pending_replan_proposal"])
        self.assertEqual(applied_state["tour_interaction_state"]["pending_action_kind"], None)

        next_state = _turn("下一个", applied_state)
        self.assertEqual(route_initial_request(next_state), "tour_event")
        result = tour_event_node(next_state)
        navigation = result["tour_presentation"]["navigation"]
        self.assertEqual(navigation.from_node_id, applied_state["tour_state"]["current_stop_id"])
        self.assertEqual(
            navigation.next_stop_id,
            applied_state["tour_interaction_state"]["pending_stop_id"],
        )
        self.assertEqual(result["tour_state"]["visited_stop_ids"], original["visited_stop_ids"])
        self.assertEqual(result["tour_state"]["skipped_stop_ids"], original["skipped_stop_ids"])

    def test_explicit_confirm_then_next_is_atomic_composite(self):
        candidate_state = self._pending_route_confirmation_state()
        before = deepcopy(candidate_state["tour_state"])
        state = _turn("使用新路线并去下一站", candidate_state)
        self.assertEqual(route_initial_request(state), "confirm_replan_and_next")
        result = confirm_replan_and_next_node(state)
        self.assertTrue(result["last_tour_event"]["ok"])
        self.assertEqual(result["last_tour_event"]["code"], "next_stop_ready")
        self.assertIsNone(result["pending_replan_proposal"])
        self.assertEqual(result["tour_state"]["current_stop_id"], before["current_stop_id"])
        self.assertEqual(result["tour_state"]["visited_stop_ids"], before["visited_stop_ids"])
        self.assertEqual(result["tour_state"]["skipped_stop_ids"], before["skipped_stop_ids"])

    def test_next_stop_never_completes_an_explaining_or_awaiting_stop(self):
        initial = self._active_state()
        arrived = tour_event_node(_turn("我到前院中部了。", initial))
        explaining_state = _turn("下一个", {**initial, **arrived})
        self.assertEqual(route_initial_request(explaining_state), "tour_event")
        explaining = tour_event_node(explaining_state)
        self.assertFalse(explaining["last_tour_event"]["ok"])
        self.assertEqual(explaining["tour_state"]["visited_stop_ids"], [])

        ended = tour_event_node(_turn("本点讲解结束", {**initial, **arrived}))
        awaiting_state = _turn("下一个", {**initial, **ended})
        self.assertEqual(route_initial_request(awaiting_state), "tour_event")
        awaiting = tour_event_node(awaiting_state)
        self.assertFalse(awaiting["last_tour_event"]["ok"])
        self.assertEqual(awaiting["tour_state"]["visited_stop_ids"], [])

    def test_next_stop_factual_request_clarifies_without_free_navigation(self):
        state = _turn("下一个点有什么木雕？", self._active_state())
        self.assertEqual(route_initial_request(state), "clarification")


if __name__ == "__main__":
    unittest.main()
