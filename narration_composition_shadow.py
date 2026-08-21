"""P3-05 audit-only Graph bridge for CardDispatcher/NarrationComposer."""

from __future__ import annotations

from typing import Any, Mapping

from card_dispatcher import dispatch_card_candidates
from controlled_knowledge_query import public_visitor_message_or_fallback
from guide_program_planner import SelectedItem, StopProgram
from guidance_evidence_bundle import CoverageCandidate
from guidance_policy import GuidancePolicy
from narration_composer import compose_narration
from narration_rendering import NarrationRenderResult
from tour_interaction import journey_mode_from_interaction


def _program(value: Mapping[str, Any]) -> StopProgram:
    items = tuple(SelectedItem(**item) for item in value.get("selected_items", []))
    return StopProgram(
        node_id=value["node_id"], display_name=value["display_name"],
        budget_seconds=value["budget_seconds"], interests=tuple(value.get("interests", [])),
        detail_level=value["detail_level"], selected_items=items,
        candidate_count=value["candidate_count"],
        budget_scope=value.get("budget_scope", "stop_explanation_content_only"),
        allocated_content_seconds=value.get("allocated_content_seconds", 0),
        unallocated_content_seconds=value.get("unallocated_content_seconds", 0),
        selection_strategy=value.get("selection_strategy", "b2_relevance_diversity_budget"),
        status=value.get("status", "ready"), guidance_policy=value.get("guidance_policy"),
    )


def _render(result: Mapping[str, Any]) -> NarrationRenderResult:
    audit = result["narration_render_audit"]
    candidates = tuple(CoverageCandidate(**value) for value in result.get("coverage_candidates", []))
    return NarrationRenderResult(
        visitor_message=result["message"],
        rendered_craft_ids=tuple(audit.get("rendered_craft_ids", [])),
        rendered_ornament_ids=tuple(audit.get("rendered_ornament_ids", [])),
        rendered_dimension_ids=tuple(audit.get("rendered_dimension_ids", [])),
        used_source_ids=tuple(audit.get("used_source_ids", [])),
        eligible_coverage_candidates=candidates,
        content_budget_seconds=audit["content_budget_seconds"],
        allocated_content_seconds=audit["allocated_content_seconds"],
        omitted_ornament_ids=tuple(audit.get("omitted_ornament_ids", [])),
        warnings=tuple(audit.get("warnings", [])),
        style_id=audit.get("style_id", "neutral"),
        style_schema_version=audit.get("style_schema_version", "narration_style_v1"),
        style_fallback_used=bool(audit.get("style_fallback_used", False)),
        style_warning_codes=tuple(audit.get("style_warning_codes", [])),
    )


def observe_narration_composition(
    *,
    thread_id: str,
    legacy_result: Mapping[str, Any],
    interaction_state: Mapping[str, Any] | None,
    visitor_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a bounded comparison record; never return an authoritative message."""
    base_record = {
        "thread_id": thread_id,
        "capability": "narration_composition",
        "mode": "shadow",
        "active_takeover": False,
        "legacy_status": legacy_result.get("status"),
    }
    if legacy_result.get("status") != "guided_e5":
        return {**base_record, "validation_status": "rejected", "rejected_reason": "legacy_e5_unavailable"}
    try:
        program = _program(legacy_result["stop_program"])
        render = _render(legacy_result)
        policy = GuidancePolicy(**legacy_result["guidance_policy"])
        remaining = max(0, render.content_budget_seconds - render.allocated_content_seconds)
        plan = dispatch_card_candidates(
            node_id=program.node_id, stop_program=program, guidance_policy=policy,
            journey_mode=journey_mode_from_interaction(dict(interaction_state or {})),
            explicit_interests=tuple((visitor_profile or {}).get("interests", [])),
            remaining_budget_seconds=remaining,
            # Stop guidance is not an explicit photo request.  Photo stays
            # closed until a later authorized intent-aware integration.
            explicit_photo_intent=False, photo_safety_cleared=False,
        )
        composed = compose_narration(stop_program=program, base_render=render, dispatch_plan=plan)
        legacy_public = public_visitor_message_or_fallback(str(legacy_result.get("message") or ""))
        return {
            **base_record,
            "validation_status": "accepted",
            "rejected_reason": None,
            "legacy_message_preserved": True,
            "candidate_public_message": composed.visitor_message,
            "same_public_message": composed.visitor_message == legacy_public,
            "candidate_card_ids": list(composed.used_card_ids),
            "omitted_card_ids": list(composed.omitted_card_ids),
            "remaining_budget_seconds": remaining,
            "candidate_warning_codes": list(composed.warnings),
            "display_tts_equal": composed.visitor_message == composed.tts_text,
            "state_writes": [],
        }
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        return {
            **base_record,
            "validation_status": "rejected",
            "rejected_reason": f"shadow_composition_failed:{type(exc).__name__}",
            "legacy_message_preserved": True,
            "active_takeover": False,
        }
