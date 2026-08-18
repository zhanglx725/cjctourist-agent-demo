"""Offline acceptance matrix for all reviewed stop-guidance role cards."""

from __future__ import annotations

import unittest
import os
from unittest.mock import patch

from langchain_core.messages import AIMessage
from agent_graph import narration_commit_node

from controlled_rollout import (
    STOP_GUIDANCE_ACTIVE_STYLE_BATCHES,
    STOP_GUIDANCE_ACTIVE_STYLES,
    competition_role_active_allowed,
)
from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_coverage import commit_introductions, empty_narration_coverage
from narration_style_policy import approved_style_ids, compile_style_brief
from narration_service_tail import build_stop_service_tail, compose_stop_presentation
from narration_validation import validate_role_narration
from role_narration_generation import RoleNarrationCandidate, apply_point_narration_scaffold
from role_narration_quality import evaluate_role_narration_shadow
from route_planner import plan_template
from tour_state import start_tour


ACTIVE_ENV = {
    "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
    "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
    "ROLE_ACTIVE_ENABLED": "true",
    "ROLE_ACTIVE_STYLES": ",".join(STOP_GUIDANCE_ACTIVE_STYLES),
    "ROLE_ACTIVE_SCENES": "route_planning,route_opening,stop_guidance",
}

POINT_FACTS = (
    ("building", NarrationFact("space:roof", "space_identity", "屋脊位于前院中部。")),
    ("craft", NarrationFact("craft:灰塑", "craft_background", "该构件采用灰塑工艺。")),
    ("ornament", NarrationFact("ornament:orn_005", "object_detail", "栏板可见花卉纹样。")),
)


def _plan(style_id: str, fact: NarrationFact) -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id="stop_front_courtyard_center", style_id=style_id, language="zh", budget_seconds=60,
        allocated_content_seconds=12, facts=(fact,), must_include=(),
        already_covered=(), must_not_claim=(),
        interaction_allowed=style_id != "listen_only",
    )


def _accepted_candidate(style_id: str, fact: NarrationFact) -> RoleNarrationCandidate:
    profile = compile_style_brief(style_id).acceptance_profile
    # The matrix uses only reviewed expression markers around one immutable
    # fact. It proves the contract for each point type without inventing venue
    # knowledge or relying on a live model response.
    connector = "，".join(profile["required_markers"])
    raw = RoleNarrationCandidate(
        style_id=style_id,
        public_text=f"{connector}，{fact.statement}",
        used_fact_ids=(fact.fact_id,), omitted_fact_ids=(),
        self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
        model_called=False, latency_ms=0,
    )
    return apply_point_narration_scaffold(
        raw, _plan(style_id, fact), compile_style_brief(style_id),
    )


class RoleNarrationStyleMatrixTests(unittest.TestCase):
    def test_all_eighteen_styles_pass_three_reviewed_point_categories(self):
        validated = 0
        for style_id in approved_style_ids():
            brief = compile_style_brief(style_id)
            for point_kind, fact in POINT_FACTS:
                with self.subTest(style_id=style_id, point_kind=point_kind):
                    candidate = _accepted_candidate(style_id, fact)
                    result = validate_role_narration(candidate, _plan(style_id, fact), brief)
                    self.assertEqual(result.validation_status, "accepted")
                    self.assertTrue(result.same_fact_boundary)
                    self.assertTrue(result.role_consistent)
                    self.assertTrue(result.public_message_safe)
                    self.assertTrue(result.layout_passed)
                    self.assertIn(fact.statement, candidate.public_text)
                    topic = fact.topic_kind
                    self.assertTrue(any(
                        value in candidate.public_text
                        for value in brief.point_narration_components[f"{topic}_intro"]
                    ))
                    self.assertNotRegex(candidate.public_text, r"(?m)【[^】]+】|^\s*(?:#|[-*+]\s|\d+[.)、]\s)")
                    self.assertNotRegex(candidate.public_text, r"～|。。|，，|source_id|node_id")
                    legacy = "【工艺背景】旧链原文。【下一步】旧链提示。"
                    tour_state = start_tour(plan_template("highlights_30"))
                    tour_state["current_stop_id"] = "stop_front_courtyard_center"
                    service_tail = build_stop_service_tail(tour_state=tour_state)
                    validation = {
                        **result.to_dict(),
                        "service_tail_validation": {
                            "validation_status": "accepted", "reason_codes": [],
                        },
                        "validated_public_message": compose_stop_presentation(
                            candidate.public_text,
                            " ".join(unit.public_text for unit in service_tail.units),
                        ),
                    }
                    with patch.dict(os.environ, ACTIVE_ENV, clear=False):
                        committed = narration_commit_node({
                            "messages": [AIMessage(id="legacy", content=legacy)],
                            "tour_state": tour_state,
                            "narration_content_plan": _plan(style_id, fact).to_dict(),
                            "role_narration_candidate": candidate.to_dict(),
                            "narration_validation": validation,
                            "active_role_narration_audit": {
                                "style_id": style_id, "state_writes": [],
                            },
                            "pending_role_narration_commit": {
                                "status": "guided_e5", "legacy_public_message": legacy,
                                "coverage_candidates": [], "narration_render_audit": {},
                                "service_tail": service_tail.to_dict(),
                            },
                            "narration_coverage": empty_narration_coverage().to_dict(),
                        })
                    audit = committed["active_role_narration_audit"]
                    self.assertTrue(audit["active_takeover"])
                    self.assertFalse(audit["fallback_used"])
                    self.assertEqual(audit["state_writes"], [])
                    self.assertNotIn("【", committed["messages"][0].content)
                    validated += 1
        self.assertEqual(validated, 54)

    def test_style_quality_failure_blocks_active_commit_eligibility(self):
        fact = POINT_FACTS[0][1]
        plan = _plan("ancient_scholar", fact)
        candidate = RoleNarrationCandidate(
            style_id="ancient_scholar", public_text=f"请看，{fact.statement}",
            used_fact_ids=(fact.fact_id,), omitted_fact_ids=(),
            self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
            model_called=False, latency_ms=0,
        )
        result = validate_role_narration(candidate, plan, compile_style_brief("ancient_scholar"))
        self.assertEqual(result.validation_status, "rejected")
        self.assertIn("style_coverage_incomplete", result.reason_codes)

    def test_shadow_matrix_is_eligible_before_active_expansion(self):
        records = []
        for style_id in approved_style_ids():
            for _, fact in POINT_FACTS:
                result = validate_role_narration(
                    _accepted_candidate(style_id, fact), _plan(style_id, fact),
                    compile_style_brief(style_id),
                )
                records.append({
                    "style_id": style_id,
                    "validation_status": result.validation_status,
                    "reason_codes": list(result.reason_codes),
                    "active_takeover": False,
                    "fallback_used": False,
                    "state_writes": [],
                    "legacy_message_preserved": True,
                })
        report = evaluate_role_narration_shadow(records)
        self.assertTrue(report["active_eligible"])
        self.assertEqual(report["decision"], "eligible_for_limited_active")
        self.assertEqual(report["sample_count"], 54)
        self.assertEqual(report["evaluated_style_count"], 18)

    def test_stop_guidance_active_expands_in_three_reviewed_batches_only(self):
        allowed = {
            style_id for style_id in approved_style_ids()
            if competition_role_active_allowed(style_id, "stop_guidance", ACTIVE_ENV)
        }
        self.assertEqual(allowed, STOP_GUIDANCE_ACTIVE_STYLES)
        self.assertEqual(len(STOP_GUIDANCE_ACTIVE_STYLE_BATCHES), 3)
        self.assertEqual(sum(map(len, STOP_GUIDANCE_ACTIVE_STYLE_BATCHES)), 18)
        for batch in STOP_GUIDANCE_ACTIVE_STYLE_BATCHES:
            batch_env = {**ACTIVE_ENV, "ROLE_ACTIVE_STYLES": ",".join(batch)}
            with self.subTest(batch=batch):
                self.assertTrue(all(
                    competition_role_active_allowed(style_id, "stop_guidance", batch_env)
                    for style_id in batch
                ))
        for style_id in approved_style_ids():
            with self.subTest(style_id=style_id):
                self.assertFalse(competition_role_active_allowed(
                    style_id, "tour_qa", ACTIVE_ENV,
                ))
                self.assertFalse(competition_role_active_allowed(
                    style_id, "navigation", ACTIVE_ENV,
                ))

    def test_commit_and_fallback_coverage_are_idempotent(self):
        record = {
            "subject_kind": "craft", "subject_id": "灰塑", "source_ids": ["S01"],
            "introduced_by": "narration_commit", "node_id": "front", "turn_id": "turn:1",
        }
        committed = commit_introductions(empty_narration_coverage(), [record])
        fallback = commit_introductions(committed, [{
            **record, "introduced_by": "deterministic_narration_fallback",
            "node_id": "front_again", "turn_id": "turn:2",
        }])
        self.assertEqual(fallback, committed)
        self.assertEqual(len(fallback.introduction_records), 1)


if __name__ == "__main__":
    unittest.main()
