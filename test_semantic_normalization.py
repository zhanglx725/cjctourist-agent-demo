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
    canonical_knowledge_plan,
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

    def test_arrival_schema_accepts_only_raw_location_text_or_null(self):
        text = "我已经晃悠到月台这边了"
        candidate = validate_candidate(text, {
            "candidate_type": "arrival",
            "evidence_span": "晃悠到月台这边",
            "location_text": "月台",
            "confidence": 0.93,
        })
        self.assertTrue(candidate.actionable)
        self.assertEqual(candidate.location_text, "月台")
        self.assertEqual(canonical_control_text(candidate), "我到月台了")

        generic = validate_candidate("我终于抵达啦", {
            "candidate_type": "arrival",
            "evidence_span": "终于抵达啦",
            "location_text": None,
            "confidence": 0.93,
        })
        self.assertEqual(canonical_control_text(generic), "我到了")

        self.assertEqual(
            validate_candidate(text, {
                "candidate_type": "arrival",
                "evidence_span": "晃悠到月台这边",
                "location_text": "前庭",
                "confidence": 0.93,
            }),
            SemanticCandidate(),
        )

    def test_duration_schema_uses_raw_time_text_and_deterministic_parser(self):
        text = "我大概还能逛半个钟头"
        candidate = validate_candidate(text, {
            "candidate_type": "remaining_duration",
            "evidence_span": "还能逛半个钟头",
            "time_text": "半个钟头",
            "time_role": "remaining",
            "confidence": 0.94,
        })
        self.assertEqual(canonical_control_text(candidate), "我还剩30分钟")
        self.assertEqual(
            validate_candidate(text, {
                "candidate_type": "remaining_duration",
                "evidence_span": "还能逛半个钟头",
                "time_text": "半小时",
                "time_role": "remaining",
                "confidence": 0.94,
            }),
            SemanticCandidate(),
        )
        unsupported = validate_candidate("我还能待一会儿", {
            "candidate_type": "remaining_duration",
            "evidence_span": "还能待一会儿",
            "time_text": "一会儿",
            "time_role": "remaining",
            "confidence": 0.94,
        })
        self.assertIsNone(canonical_control_text(unsupported))

    def test_extra_or_model_execution_fields_fail_closed(self):
        base = {
            "candidate_type": "arrival",
            "evidence_span": "我到啦",
            "location_text": None,
            "confidence": 0.93,
        }
        for field, value in {
            "node_id": "label_moon_platform",
            "route": "dynamic_30",
            "route_id": "highlights_30",
            "source_ids": ["S10"],
            "query": "石雕",
            "categories": ["ornament_craft"],
            "answer": "...",
            "state_update": {"x": 1},
            "minutes": 30,
            "tool": "route_planner",
        }.items():
            with self.subTest(field=field):
                self.assertEqual(
                    validate_candidate("我到啦", {**base, field: value}),
                    SemanticCandidate(),
                )

    def test_fact_candidate_maps_only_to_existing_reviewed_fact_kind(self):
        text = "陈家祠最晚什么时候还能进入？"
        candidate = validate_candidate(text, {
            "candidate_type": "fact_last_admission",
            "evidence_span": "最晚什么时候还能进入",
            "confidence": 0.95,
        })
        self.assertTrue(candidate.actionable)
        self.assertEqual(canonical_fact_kind(candidate), "last_admission")
        self.assertIsNone(canonical_control_text(candidate))

    def test_knowledge_candidate_maps_to_read_only_plan(self):
        text = "三顾茅庐讲了什么故事？"
        candidate = validate_candidate(text, {
            "candidate_type": "knowledge_query",
            "evidence_span": "三顾茅庐",
            "confidence": 0.95,
            "knowledge_domain": "ornament_item",
            "question_type": "story",
            "detail_level": "brief",
        })
        plan = canonical_knowledge_plan(candidate)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.subject_text, "三顾茅庐")
        self.assertEqual(plan.categories, ("ornament_item",))

    def test_invalid_enum_low_confidence_invalid_json_and_model_failure_are_no_ops(self):
        low = validate_candidate("帮我随便逛逛", {
            "candidate_type": "route_request",
            "evidence_span": "随便逛逛",
            "confidence": 0.89,
        })
        self.assertFalse(low.actionable)
        self.assertEqual(
            validate_candidate("我到啦", {
                "candidate_type": "not_allowed",
                "evidence_span": "我到啦",
                "confidence": 0.95,
            }),
            SemanticCandidate(),
        )
        self.assertEqual(
            recognize_semantic_candidate("我到啦", lambda _: "not json"),
            SemanticCandidate(),
        )
        self.assertEqual(
            recognize_semantic_candidate("我到啦", lambda _: (_ for _ in ()).throw(RuntimeError("offline"))),
            SemanticCandidate(),
        )

    def test_minimize_walking_is_a_candidate_not_a_hidden_route_change(self):
        candidate = validate_candidate("帮我安排一条少走路的路线", {
            "candidate_type": "route_request_minimize_walking",
            "evidence_span": "少走路的路线",
            "confidence": 0.95,
        })
        self.assertEqual(canonical_control_text(candidate), "帮我规划一条少走路的路线")
        self.assertEqual(candidate.to_dict()["candidate_type"], "route_request_minimize_walking")

    def test_normalized_arrival_still_uses_existing_pending_stop_guard(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线"))
        state = self._state("我终于抵达啦", initial)
        candidate = SemanticCandidate(
            candidate_type="arrival", evidence_span="终于抵达啦", confidence=0.95,
            location_text=None,
        )
        with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
            state.update(semantic_normalization_node(state))
        self.assertEqual(route_initial_request(state), "tour_event")
        arrived = tour_event_node(state)
        self.assertEqual(
            arrived["last_tour_intent"]["arguments"]["node_id"],
            initial["tour_interaction_state"]["pending_stop_id"],
        )

    def test_normalized_remaining_time_still_uses_existing_profile_update(self):
        initial = direct_route_node(self._state("我有60分钟，帮我规划路线"))
        state = self._state("我还能待半个钟头", initial)
        candidate = SemanticCandidate(
            candidate_type="remaining_duration", evidence_span="还能待半个钟头",
            confidence=0.95, time_text="半个钟头", time_role="remaining",
        )
        with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
            state.update(semantic_normalization_node(state))
        self.assertEqual(route_initial_request(state), "profile_update")
        result = profile_update_node(state)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 30)

    def test_pending_replan_controls_never_call_the_model(self):
        route_pending = {
            "pending_replan_proposal": {"status": "awaiting_route_confirmation"},
        }
        time_pending = {"pending_replan_time_confirmation": {"status": "awaiting_confirmation"}}
        cases = (
            (route_pending, "确认"),
            (route_pending, "确认新路线"),
            (route_pending, "使用这条路线"),
            (route_pending, "继续原路线"),
            (route_pending, "取消调整"),
            (time_pending, "我还有30分钟"),
            (time_pending, "按半小时安排"),
            (time_pending, "就按刚才的时间"),
            (route_pending, "再说一下新路线"),
            (route_pending, "新路线有哪些点"),
        )
        for pending, text in cases:
            with self.subTest(text=text), patch("agent_graph.recognize_semantic_candidate") as recognizer:
                result = semantic_normalization_node(self._state(text, pending))
            recognizer.assert_not_called()
            metric = result["performance_metrics"][-1]
            self.assertEqual(metric["status"], "not_needed")
            self.assertFalse(metric["model_called"])
            self.assertEqual(metric["reason"], "pending_replan_confirmation")

    def test_explicit_specialist_request_skips_model_before_broad_plan(self):
        state = self._state("石雕是什么？")
        with patch("agent_graph.recognize_semantic_candidate") as recognizer:
            result = semantic_normalization_node(state)
        recognizer.assert_not_called()
        self.assertIsNone(result["knowledge_query_plan"])
        self.assertEqual(result["performance_metrics"][-1]["reason"], "specialist_channel")

    def test_existing_deterministic_knowledge_plan_still_skips_model(self):
        state = self._state("团队订单电子发票规则")
        with patch("agent_graph.recognize_semantic_candidate") as recognizer:
            result = semantic_normalization_node(state)
        recognizer.assert_not_called()
        self.assertEqual(result["performance_metrics"][-1]["status"], "deterministic_knowledge_plan")
        self.assertFalse(result["performance_metrics"][-1]["model_called"])
        self.assertEqual(result["knowledge_query_plan"]["domain"], "ticketing")


if __name__ == "__main__":
    unittest.main()
