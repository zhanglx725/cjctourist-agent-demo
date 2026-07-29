"""Offline tests for the closed semantic-normalization gate."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    direct_route_node,
    profile_update_node,
    route_initial_request,
    semantic_normalization_node,
    tour_event_node,
)
from semantic_normalization import (
    SemanticCandidate,
    canonical_control_text,
    canonical_fact_kind,
    recognize_semantic_candidate,
    validate_candidate,
)


class SemanticNormalizationTests(unittest.TestCase):
    @staticmethod
    def _state(text: str, initial: dict | None = None) -> dict:
        state = dict(initial or {})
        state["messages"] = [HumanMessage(content=text)]
        state["performance_metrics"] = []
        return state

    def test_valid_unlisted_arrival_is_canonicalized_without_a_node_id(self):
        text = "我终于抵达啦"
        candidate = validate_candidate(text, {
            "candidate_kind": "generic_arrival", "evidence_text": "终于抵达啦",
            "confidence": "high", "minutes": None,
        })
        self.assertTrue(candidate.actionable)
        self.assertEqual(canonical_control_text(candidate), "我到了")

    def test_duration_requires_a_positive_integer_and_exact_user_evidence(self):
        text = "我大概还能待四十来分钟"
        candidate = validate_candidate(text, {
            "candidate_kind": "remaining_duration", "evidence_text": "还能待四十来分钟",
            "confidence": "high", "minutes": 40,
        })
        self.assertEqual(canonical_control_text(candidate), "我还剩40分钟")
        invalid = validate_candidate(text, {
            "candidate_kind": "remaining_duration", "evidence_text": "还有一小时",
            "confidence": "high", "minutes": 60,
        })
        self.assertFalse(invalid.actionable)

    def test_schema_extra_fields_and_node_ids_fail_closed(self):
        candidate = validate_candidate("我到啦", {
            "candidate_kind": "generic_arrival", "evidence_text": "我到啦",
            "confidence": "high", "minutes": None, "node_id": "stop_front_courtyard_center",
        })
        self.assertEqual(candidate, SemanticCandidate())

    def test_fact_candidate_maps_only_to_an_existing_reviewed_fact_kind(self):
        text = "陈家祠最晚什么时候还能进入？"
        candidate = validate_candidate(text, {
            "candidate_kind": "fact_last_admission",
            "evidence_text": "最晚什么时候还能进入",
            "confidence": "high",
            "minutes": None,
        })
        self.assertTrue(candidate.actionable)
        self.assertEqual(canonical_fact_kind(candidate), "last_admission")
        self.assertIsNone(canonical_control_text(candidate))

    def test_fact_candidate_cannot_generate_query_category_or_minutes(self):
        text = "陈家祠一般哪天歇着？"
        generated_query = validate_candidate(text, {
            "candidate_kind": "fact_closed_day",
            "evidence_text": "哪天歇着",
            "confidence": "high",
            "minutes": None,
            "query": "周二闭馆",
        })
        self.assertEqual(generated_query, SemanticCandidate())
        invalid_minutes = validate_candidate(text, {
            "candidate_kind": "fact_closed_day",
            "evidence_text": "哪天歇着",
            "confidence": "high",
            "minutes": 2,
        })
        self.assertEqual(invalid_minutes, SemanticCandidate())

    def test_unlisted_fact_paraphrase_is_stored_without_rewriting_user_text(self):
        state = self._state("陈家祠一般哪天歇着？")
        with patch(
            "agent_graph.recognize_semantic_candidate",
            return_value=SemanticCandidate(
                "fact_closed_day", "哪天歇着", "high"
            ),
        ):
            normalized = semantic_normalization_node(state)
        state.update(normalized)
        self.assertEqual(state["semantic_fact_kind"], "closed_day")
        self.assertIsNone(state["semantic_control_text"])
        self.assertEqual(route_initial_request(state), "direct_rag")

    def test_low_confidence_and_model_failures_are_no_ops(self):
        low = validate_candidate("带我随便逛逛", {
            "candidate_kind": "route_request", "evidence_text": "随便逛逛",
            "confidence": "low", "minutes": None,
        })
        self.assertFalse(low.actionable)
        failed = recognize_semantic_candidate("我到啦", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(failed, SemanticCandidate())

    def test_minimize_walking_is_a_candidate_not_a_hidden_route_change(self):
        candidate = validate_candidate("帮我安排一条少走路的路线", {
            "candidate_kind": "route_request_minimize_walking", "evidence_text": "少走路的路线",
            "confidence": "high", "minutes": None,
        })
        self.assertEqual(
            canonical_control_text(candidate), "帮我规划一条少走路的路线"
        )
        self.assertEqual(candidate.to_dict()["candidate_kind"], "route_request_minimize_walking")

    def test_normalized_arrival_still_uses_existing_pending_stop_guard(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线"))
        state = self._state("我终于抵达啦", initial)
        with patch("agent_graph.recognize_semantic_candidate", return_value=SemanticCandidate(
            "generic_arrival", "终于抵达啦", "high"
        )):
            normalized = semantic_normalization_node(state)
        state.update(normalized)
        self.assertEqual(route_initial_request(state), "tour_event")
        arrived = tour_event_node(state)
        self.assertEqual(arrived["last_tour_intent"]["arguments"]["node_id"], initial["tour_interaction_state"]["pending_stop_id"])

    def test_normalized_remaining_time_still_uses_existing_profile_update(self):
        initial = direct_route_node(self._state("我有60分钟，帮我规划路线"))
        state = self._state("我大概还能待四十来分钟", initial)
        with patch("agent_graph.recognize_semantic_candidate", return_value=SemanticCandidate(
            "remaining_duration", "还能待四十来分钟", "high", 40
        )):
            state.update(semantic_normalization_node(state))
        self.assertEqual(route_initial_request(state), "profile_update")
        result = profile_update_node(state)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 40)


if __name__ == "__main__":
    unittest.main()
