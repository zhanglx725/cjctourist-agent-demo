"""Runnable evaluation entry for the role-narration graph segment.

It deliberately runs the production generation, validation, commit and
fallback nodes.  Dataset fixtures provide an already-reviewed ContentPlan, so
this is not a substitute for a full visitor conversation beginning at
``stop_guidance``; that distinction is returned in every result.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from langchain_core.messages import AIMessage

from agent_graph import (
    deterministic_narration_fallback_node,
    narration_commit_node,
    narration_validation_node,
    role_narration_generation_node,
)
from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_coverage import empty_narration_coverage
from role_narration_generation import RoleNarrationCandidate
from role_narration_style_evaluator import evaluate_role_narration_style


@contextmanager
def _temporary_environment(values: Mapping[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _active_environment(style_id: str) -> dict[str, str]:
    return {
        "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
        "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
        "ROLE_ACTIVE_ENABLED": "true",
        "ROLE_ACTIVE_STYLES": style_id,
        "ROLE_ACTIVE_SCENES": "stop_guidance",
    }


def _legacy_message(fact: str) -> str:
    return f"【审核点位讲解】\n\n{fact}\n\n【下一步】\n\n可继续前往下一处。"


def _state(inputs: Mapping[str, Any]) -> dict[str, Any]:
    fact = str(inputs["approved_fact"])
    fact_id = str(inputs["fact_id"])
    style_id = str(inputs["style_id"])
    legacy = _legacy_message(fact)
    plan = NarrationContentPlan(
        stop_id="langsmith_fixture_stop", style_id=style_id, language="zh",
        budget_seconds=60, allocated_content_seconds=12,
        facts=(NarrationFact(fact_id, "evaluation_fact", fact),),
        must_include=(), already_covered=(), must_not_claim=(),
        # The first uploaded fault dataset predates this explicit field.  Keep
        # those remote examples executable while treating listen-only as the
        # only non-interactive contract.
        interaction_allowed=bool(inputs.get("interaction_allowed", style_id != "listen_only")),
    )
    coverage_candidates = []
    rendered_crafts: list[str] = []
    rendered_ornaments: list[str] = []
    if fact_id.startswith("craft:"):
        subject_id = fact_id.removeprefix("craft:")
        rendered_crafts = [subject_id]
        coverage_candidates = [{
            "subject_kind": "craft", "subject_id": subject_id,
            "source_ids": ["S10"], "evidence_kind": "craft_overview",
            "node_id": "langsmith_fixture_stop",
        }]
    elif fact_id.startswith("ornament:"):
        subject_id = fact_id.removeprefix("ornament:")
        rendered_ornaments = [subject_id]
        coverage_candidates = [{
            "subject_kind": "ornament", "subject_id": subject_id,
            "source_ids": ["S11"], "evidence_kind": "ornament_detail",
            "node_id": "langsmith_fixture_stop",
        }]
    return {
        "messages": [AIMessage(id="langsmith-fixture-message", content=legacy)],
        "narration_content_plan": plan.to_dict(),
        "role_mode_shadow": {
            "status": "selected", "selected_style_id": style_id,
            "source": "langsmith_dataset", "confidence": 1.0,
        },
        "narration_coverage": empty_narration_coverage().to_dict(),
        "tour_state": {"current_stop_id": "langsmith_fixture_stop"},
        "pending_role_narration_commit": {
            "status": "guided_e5", "legacy_public_message": legacy,
            "coverage_candidates": coverage_candidates,
            "narration_render_audit": {
                "node_id": "langsmith_fixture_stop",
                "rendered_craft_ids": rendered_crafts,
                "rendered_ornament_ids": rendered_ornaments,
                "used_source_ids": ["S10", "S11"],
            },
        },
        "tour_presentation": {"message": legacy, "ok": True},
    }


def _fault_candidate(inputs: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return deliberate malformed prose for non-model fallback cases only."""
    failure_type = str(inputs.get("failure_type") or "")
    if failure_type not in {"fact_drift", "style_forbidden", "interaction_violation", "internal_leak"}:
        return None
    fact = str(inputs["approved_fact"])
    fact_id = str(inputs["fact_id"])
    style_id = str(inputs["style_id"])
    connector = {
        "fact_drift": "另有传说称此处建于1900年，",
        "style_forbidden": "绝绝子，",
        "internal_leak": "source_ids=evaluation_fixture，",
    }.get(failure_type)
    if failure_type == "interaction_violation":
        connector = (
            "请攀爬拍照，" if style_id == "photo_guide"
            else "强制互动任务，" if style_id == "exploration_game"
            else "请你拍照好吗？"
        )
    return RoleNarrationCandidate(
        style_id=style_id, public_text=f"{connector}{fact}",
        used_fact_ids=(fact_id,), omitted_fact_ids=(),
        self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
        model_called=False, latency_ms=0,
    ).to_dict()


def _deterministic_assertions(
    inputs: Mapping[str, Any], outputs: Mapping[str, Any], result: Mapping[str, Any],
) -> dict[str, bool]:
    validation = result["validation"]
    audit = result["commit_audit"]
    final_message = str(result["final_visitor_message"])
    expected_fact = str(inputs["approved_fact"])
    expected_count = int(outputs.get("expected_coverage_commit_count", 0))
    records = result["coverage"].get("introduction_records", [])
    fallback_expected = bool(outputs.get("expected_fallback_on_validation_failure", False))
    should_fallback = bool(inputs.get("failure_type"))
    return {
        "scene_kind_matches": result["scene_kind"] == "stop_guidance",
        "approved_fact_verbatim": expected_fact in final_message,
        "no_internal_field_leak": "source_ids=" not in final_message and "node_id=" not in final_message,
        "state_writes_empty": audit.get("state_writes") == [],
        "active_or_fallback_decision_matches": (
            audit.get("fallback_used") if should_fallback else audit.get("active_takeover")
        ),
        "fallback_contract_present": (
            fallback_expected if not should_fallback
            else bool(audit.get("fallback_used"))
        ),
        "coverage_commit_count_matches": len(records) == expected_count,
        "coverage_has_no_duplicates": len(records) == len({
            (record["subject_kind"], record["subject_id"]) for record in records
        }),
        "validation_is_consistent_with_publication": (
            validation["validation_status"] == "accepted"
        ) == bool(audit.get("active_takeover")),
    }


def run_role_narration_example(
    inputs: Mapping[str, Any], expected_outputs: Mapping[str, Any] | None = None,
    *, enable_tracing: bool = False, evaluate_style_quality: bool = False,
) -> dict[str, Any]:
    """Run the production graph segment and return only evaluation-safe audit fields."""
    state = _state(inputs)
    outputs = dict(expected_outputs or {})
    failure_type = str(inputs.get("failure_type") or "")
    injected_failure = {
        "model_failure": "timeout",
        "budget_exceeded": "budget_exceeded",
    }.get(failure_type, "")
    with _temporary_environment({
        **_active_environment(str(inputs["style_id"])),
        "CJC_ROLE_NARRATION_TEST_FAILURE": injected_failure,
        # Dataset runners enable tracing explicitly. Direct unit calls remain
        # offline and deterministic even when a developer's .env enables it.
        "LANGSMITH_TRACING": None if enable_tracing else "false",
        "LANGCHAIN_TRACING_V2": None if enable_tracing else "false",
    }):
        injected_candidate = _fault_candidate(inputs)
        generated = (
            {"role_narration_candidate": injected_candidate}
            if injected_candidate is not None
            else role_narration_generation_node(state)
        )
        merged = {**state, **generated}
        validated = narration_validation_node(merged)
        merged = {**merged, **validated}
        if validated["narration_validation"]["validation_status"] == "accepted":
            published = narration_commit_node(merged)
        else:
            published = deterministic_narration_fallback_node(merged)
    audit = published["active_role_narration_audit"]
    final_message = (
        published.get("messages", [state["messages"][-1]])[-1].content
        if published.get("messages") else state["messages"][-1].content
    )
    result = {
        "evaluation_entry": "production_role_narration_graph_segment",
        "full_stop_guidance_session": False,
        "style_id": inputs["style_id"],
        "scene_kind": "stop_guidance",
        "candidate": generated["role_narration_candidate"],
        "validation": validated["narration_validation"],
        "commit_audit": audit,
        "final_visitor_message": final_message,
        "coverage": published["narration_coverage"],
    }
    result["assertions"] = _deterministic_assertions(inputs, outputs, result)
    result["style_quality"] = (
        evaluate_role_narration_style(
            style_id=str(inputs["style_id"]), public_text=final_message,
        )
        if evaluate_style_quality and audit.get("active_takeover")
        else {"status": "not_requested"}
    )
    return result
