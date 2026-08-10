"""Offline tests for the closed semantic-normalization gate."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    direct_route_node,
    profile_update_node,
    route_initial_request,
    semantic_normalization_node,
    tour_event_node,
)
from tour_intent import looks_like_arrival_control, resolve_reviewed_node
from semantic_normalization import (
    SemanticCandidate,
    canonical_control_text,
    canonical_fact_kind,
    canonical_knowledge_plan,
    is_safe_arrival_candidate,
    is_safe_arrival_report_text,
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

    def test_multi_candidate_envelope_keeps_order_and_legacy_primary(self):
        raw = json.dumps({
            "candidates": [
                {"candidate_type": "route_request", "evidence_span": "规划路线", "confidence": 0.93},
                {"candidate_type": "available_duration", "evidence_span": "30分钟", "time_text": "30分钟", "time_role": "available", "confidence": 0.95},
            ],
            "ambiguity_reason": None,
        }, ensure_ascii=False)
        candidate = recognize_semantic_candidate("30分钟，帮我规划路线", lambda _: raw)
        self.assertEqual(candidate.candidate_type, "available_duration")
        self.assertEqual([item.candidate_type for item in candidate.alternatives], ["route_request"])

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

    def test_c1_generalized_arrival_reports_bind_only_the_unique_pending_stop(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        pending = initial["tour_interaction_state"]["pending_stop_id"]
        for text in (
            "我已经走到这一站跟前了。",
            "我人已经到这儿了。",
            "刚刚走到该看的地方。",
            "我已经到目的地了。",
            "人已经到位了。",
        ):
            with self.subTest(text=text):
                candidate = SemanticCandidate(
                    candidate_type="arrival",
                    evidence_span=text.rstrip("。"),
                    confidence=0.95,
                    location_text=None,
                )
                self.assertTrue(is_safe_arrival_candidate(text, candidate))
                state = self._state(text, initial)
                with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
                    state.update(semantic_normalization_node(state))
                # Some C1 wording is already recognized by the deterministic
                # A1 parser; the remaining variants enter through the semantic
                # candidate.  Both must converge on the same existing event.
                if state.get("semantic_control_text") is not None:
                    self.assertEqual(state["semantic_control_text"], "我到了")
                self.assertEqual(route_initial_request(state), "tour_event")
                arrived = tour_event_node(state)
                self.assertEqual(arrived["last_tour_event"]["code"], "arrived")
                self.assertEqual(arrived["tour_state"]["current_stop_id"], pending)
                self.assertEqual(arrived["tour_state"]["visited_stop_ids"], [])
                self.assertEqual(arrived["tour_interaction_state"]["stop_phase"], "explaining")
                audit = arrived["semantic_arrival_audit"]
                # Directly recognized C1 wording has no model-candidate audit;
                # model-normalized wording retains the resolution trace.
                if audit is not None:
                    self.assertEqual(audit["resolved_node_id"], pending)
                    self.assertEqual(audit["final_event"]["code"], "arrived")

    def test_c1_explicit_arrival_uses_reviewed_resolution_and_nonpending_reuses_p1_11(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        before = {
            key: initial.get(key)
            for key in ("visitor_profile", "active_route_plan", "active_stop_program")
        }
        text = "我已经晃悠到后庭这边了。"
        candidate = SemanticCandidate(
            candidate_type="arrival",
            evidence_span="晃悠到后庭这边",
            confidence=0.95,
            location_text="后庭",
        )
        state = self._state(text, initial)
        with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
            state.update(semantic_normalization_node(state))
        # The deterministic reviewed-node parser now owns this explicit raw
        # arrival before semantic normalization.  A semantic audit is
        # therefore optional; the A1 self-arrival outcome below remains the
        # required verification.
        self.assertIsNone(state["semantic_arrival_audit"])
        self.assertEqual(route_initial_request(state), "tour_event")
        result = tour_event_node(state)
        self.assertEqual(result["last_tour_event"]["code"], "self_arrival")
        self.assertEqual(result["tour_state"]["current_stop_id"], "stop_rear_courtyard")
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_interaction_state"]["stop_phase"], "navigating")
        self.assertEqual(
            result["pending_replan_time_confirmation"]["status"],
            "replan_time_confirmation",
        )
        self.assertIsNone(result["semantic_arrival_audit"])
        merged = {**initial, **result}
        for key, value in before.items():
            self.assertEqual(merged.get(key), value)

    def test_c1_explicit_arrival_location_text_is_raw_and_resolved_only_by_reviewed_nodes(self):
        cases = (
            ("我已经晃悠到月台这边了。", "晃悠到月台这边", "月台", "label_moon_platform"),
            ("现在人就在前庭。", "现在人就在前庭", "前庭", "stop_front_courtyard_north"),
            ("刚走进后庭。", "刚走进后庭", "后庭", "stop_rear_courtyard"),
            ("我们已经来到后东庭了。", "来到后东庭了", "后东庭", "stop_rear_east_courtyard_inner"),
        )
        for text, evidence_span, location_text, expected_node_id in cases:
            with self.subTest(text=text):
                candidate = SemanticCandidate(
                    candidate_type="arrival",
                    evidence_span=evidence_span,
                    confidence=0.95,
                    location_text=location_text,
                )
                self.assertTrue(is_safe_arrival_candidate(text, candidate))
                self.assertEqual(candidate.location_text, location_text)
                self.assertIn(candidate.location_text, text)
                self.assertEqual(
                    resolve_reviewed_node(candidate.location_text).node_id,
                    expected_node_id,
                )

    def test_c1_arrival_guard_rejects_intent_transit_negation_questions_and_third_party(self):
        for text in (
            "我想去月台。",
            "我快到月台了。",
            "我还没到月台。",
            "如果我到月台怎么办？",
            "我是不是到前庭了？",
            "月台有什么？",
            "我朋友到月台了。",
            "我到月台了，顺便跳过前庭。",
        ):
            with self.subTest(text=text):
                candidate = SemanticCandidate(
                    candidate_type="arrival",
                    evidence_span=text.rstrip("。？"),
                    confidence=0.95,
                    location_text="月台" if "月台" in text else None,
                )
                self.assertFalse(is_safe_arrival_report_text(text))
                self.assertFalse(is_safe_arrival_candidate(text, candidate))

    def test_c1_rejected_arrival_candidates_leave_existing_tour_state_unchanged(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        protected_keys = (
            "tour_state", "tour_interaction_state", "visitor_profile",
            "active_route_plan", "active_stop_program",
        )
        before = {key: deepcopy(initial.get(key)) for key in protected_keys}
        for text in (
            "我想去月台。",
            "我快到月台了。",
            "我还没到月台。",
            "如果我到月台怎么办？",
            "我朋友到月台了。",
            "我到月台了，顺便跳过前庭。",
        ):
            with self.subTest(text=text):
                candidate = SemanticCandidate(
                    candidate_type="arrival",
                    evidence_span=text.rstrip("。？"),
                    confidence=0.95,
                    location_text="月台",
                )
                state = self._state(text, initial)
                with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
                    state.update(semantic_normalization_node(state))
                self.assertNotEqual(route_initial_request(state), "tour_event")
                for key, value in before.items():
                    self.assertEqual(state.get(key), value)

    def test_c1_generic_arrival_without_route_does_not_create_state(self):
        candidate = SemanticCandidate(
            candidate_type="arrival", evidence_span="人已经到位了", confidence=0.95,
            location_text=None,
        )
        state = self._state("人已经到位了。")
        with patch("agent_graph.recognize_semantic_candidate", return_value=candidate):
            update = semantic_normalization_node(state)
        state.update(update)
        self.assertEqual(route_initial_request(state), "clarification")
        self.assertNotIn("tour_state", state)

    def test_c1_high_frequency_arrival_forms_are_deterministic_and_do_not_call_model(self):
        """Studio arrival wording must reach A1 without semantic/RAG fallback."""
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        pending = initial["tour_interaction_state"]["pending_stop_id"]
        for text in (
            "我已经抵达这里了。",
            "我人到了。",
            "终于走到了。",
            "已经来到这一站了。",
            "我们走到跟前了。",
        ):
            with self.subTest(text=text), patch("agent_graph.recognize_semantic_candidate") as recognizer:
                state = self._state(text, initial)
                state.update(semantic_normalization_node(state))
            recognizer.assert_not_called()
            metric = state["performance_metrics"][-1]
            self.assertFalse(metric["model_called"])
            self.assertEqual(route_initial_request(state), "tour_event")
            arrived = tour_event_node(state)
            self.assertEqual(arrived["last_tour_event"]["code"], "arrived")
            self.assertEqual(arrived["tour_state"]["current_stop_id"], pending)
            self.assertEqual(arrived["tour_state"]["visited_stop_ids"], [])
            visitor_message = str(arrived["messages"][-1].content)
            self.assertNotRegex(visitor_message, r"(?i)(?:\.md\b|S\d{2}\b|https?://|原始chunk)")

    def test_c1_explicit_arrival_forms_resolve_raw_location_and_reuse_p1_11(self):
        """Explicit locations come from user text and non-pending arrival deviates safely."""
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        cases = (
            ("终于走到月台了。", "月台", "label_moon_platform", True),
            ("我已经抵达后庭了。", "后庭", "stop_rear_courtyard", True),
            ("我们来到前庭了。", "前庭", "stop_front_courtyard_north", True),
        )
        for text, location_text, node_id, is_deviation in cases:
            with self.subTest(text=text), patch("agent_graph.recognize_semantic_candidate") as recognizer:
                state = self._state(text, initial)
                state.update(semantic_normalization_node(state))
            recognizer.assert_not_called()
            self.assertEqual(resolve_reviewed_node(location_text).node_id, node_id)
            self.assertEqual(route_initial_request(state), "tour_event")
            result = tour_event_node(state)
            self.assertEqual(result["tour_state"]["current_stop_id"], node_id)
            self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
            if is_deviation:
                self.assertEqual(result["last_tour_event"]["code"], "self_arrival")
                self.assertEqual(result["pending_replan_time_confirmation"]["status"], "replan_time_confirmation")
            else:
                self.assertEqual(result["last_tour_event"]["code"], "arrived")

    def test_c1_arrival_shaped_failures_clarify_without_model_or_state_write(self):
        initial = direct_route_node(self._state("我有30分钟，帮我规划路线。"))
        protected_keys = (
            "tour_state", "tour_interaction_state", "visitor_profile",
            "active_route_plan", "active_stop_program",
        )
        before = {key: deepcopy(initial.get(key)) for key in protected_keys}
        for text in (
            "我还没抵达月台。",
            "我人还在路上。",
            "我准备去月台。",
            "我快走到月台了。",
            "如果到了月台。",
            "我是不是到月台了？",
            "朋友已经抵达月台。",
            # This has arrival shape but no resolvable point and no generic
            # completion phrase, so it exercises the no-model fail-closed path.
            "我刚抵达那边。",
        ):
            with self.subTest(text=text), patch("agent_graph.recognize_semantic_candidate") as recognizer:
                self.assertTrue(looks_like_arrival_control(text))
                state = self._state(text, initial)
                state.update(semantic_normalization_node(state))
            recognizer.assert_not_called()
            self.assertEqual(route_initial_request(state), "clarification")
            for key, value in before.items():
                self.assertEqual(state.get(key), value)

    def test_c1_arrival_guard_does_not_intercept_temporal_or_place_knowledge_questions(self):
        for text in ("月台有什么？", "讲讲月台。", "月台的石雕有什么特点？", "到达月台后能看到什么？", "为什么路线要经过月台？"):
            with self.subTest(text=text):
                self.assertFalse(looks_like_arrival_control(text))
                state = self._state(text)
                with patch("agent_graph.recognize_semantic_candidate", return_value=SemanticCandidate()):
                    state.update(semantic_normalization_node(state))
                self.assertNotEqual(route_initial_request(state), "tour_event")
                self.assertNotEqual(route_initial_request(state), "clarification")

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

    def test_deterministic_route_request_has_auditable_envelope_candidate(self):
        state = self._state("中文，经典模式，我有30分钟，请规划少走路路线")
        with patch("agent_graph.recognize_semantic_candidate") as recognizer:
            result = semantic_normalization_node(state)
        recognizer.assert_not_called()
        envelope = result["semantic_intent_envelope"]
        self.assertFalse(envelope["model_called"])
        self.assertEqual(envelope["candidates"][0]["intent"], "request_route")
        self.assertEqual(envelope["candidates"][0]["arguments"]["available_minutes"], 30)
        self.assertTrue(envelope["candidates"][0]["arguments"]["minimize_walking"])


if __name__ == "__main__":
    unittest.main()
