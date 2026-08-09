"""Strict, read-only presentation planning for the five public tour scenes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from narration_style_policy import approved_style_ids


PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION = "presentation_content_plan_v1"
SCENE_KINDS = frozenset(
    {"route_planning", "route_opening", "stop_guidance", "navigation", "tour_closing"}
)
ROLE_MODE_IDS = frozenset({"standard", *approved_style_ids()})
DETAIL_LEVELS = frozenset({"short", "standard", "deep"})
FALLBACK_MODES = frozenset({"legacy_chain"})

_SOURCE_LABELS = frozenset(
    {
        "visitor_profile", "guidance_policy", "route_selection", "route_stop_catalog",
        "tour_opening_evidence", "stop_program", "approved_guidance_evidence",
        "approved_spatial_graph", "tour_state", "visit_summary", "narration_coverage",
    }
)
_INTERNAL_MARKERS = (
    "node_id", "ornament_id", "route_id", "source_ids", "tourstate", "visitorprofile",
    "rag_tool", "http://", "https://", "c:\\", "\\data\\",
)
_SCENE_SECTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "route_planning": (("route_overview", "interest_coverage", "route_strategy", "stay_and_walk_estimate", "next_action"), ("site_conditions", "uncovered_interests")),
    "route_opening": (("route_theme", "total_duration", "stop_order", "first_stop", "visit_notes"), ("observation_expectation",)),
    "stop_guidance": (("craft_or_theme_background", "reviewed_objects", "observation_location", "observation_task", "completion_control"), ("comparison_hint", "photo_safety")),
    "navigation": (("current_location", "next_stop", "approved_path", "walk_time", "site_uncertainty"), ("arrival_action",)),
    "tour_closing": (("completed_summary", "unfinished_items", "return_or_exit_advice", "no_inferred_visitor_result"), ("follow_up_options",)),
}
_BASE_SAFETY = ("preserve_venue_rules", "preserve_staff_and_signage_instructions", "do_not_invent_visitor_actions")


class PresentationContentPlanError(ValueError):
    """Raised when a plan cannot be represented within the closed contract."""


def _contains_internal_marker(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_internal_marker(k) or _contains_internal_marker(v) for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_internal_marker(item) for item in value)
    if isinstance(value, str):
        lowered = value.casefold()
        return any(marker in lowered for marker in _INTERNAL_MARKERS)
    return False


def _tuple_strings(values: Iterable[str] | None, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise PresentationContentPlanError(f"{field}_must_contain_non_empty_strings")
    if _contains_internal_marker(result):
        raise PresentationContentPlanError(f"{field}_contains_internal_field")
    return result


@dataclass(frozen=True)
class PresentationContentPlan:
    schema_version: str
    scene_kind: str
    role_mode: str
    detail_level: str
    content_goal: str
    required_sections: tuple[str, ...]
    optional_sections: tuple[str, ...]
    observation_tasks: tuple[str, ...]
    safety_requirements: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    budget_seconds: int
    fallback_mode: str
    source_of_facts: tuple[str, ...]
    status: str = "accepted"
    reason_codes: tuple[str, ...] = ()
    state_writes: tuple[str, ...] = ()
    legacy_message_preserved: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("required_sections", "optional_sections", "observation_tasks", "safety_requirements", "evidence_requirements", "reason_codes", "state_writes", "source_of_facts"):
            data[key] = list(data[key])
        return data


def _rejected(reason: str, *, scene_kind: str | None = None, role_mode: str | None = None) -> PresentationContentPlan:
    return PresentationContentPlan(
        schema_version=PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION,
        scene_kind=scene_kind or "unknown", role_mode=role_mode or "standard", detail_level="standard",
        content_goal="legacy_chain_fallback", required_sections=(), optional_sections=(), observation_tasks=(),
        safety_requirements=_BASE_SAFETY, evidence_requirements=("approved_evidence_required",), budget_seconds=0,
        fallback_mode="legacy_chain", source_of_facts=(), status="rejected", reason_codes=(reason,),
    )


def build_presentation_content_plan(
    *, scene_kind: str, role_mode: str = "standard", detail_level: str = "standard", budget_seconds: int,
    source_of_facts: Iterable[str], evidence_available: bool = True,
    observation_tasks: Iterable[str] | None = None, optional_sections: Iterable[str] | None = None,
) -> PresentationContentPlan:
    """Build a closed, source-free plan; invalid input fails closed."""
    try:
        if scene_kind not in SCENE_KINDS:
            raise PresentationContentPlanError("invalid_scene_kind")
        if role_mode not in ROLE_MODE_IDS:
            raise PresentationContentPlanError("invalid_role_mode")
        if detail_level not in DETAIL_LEVELS:
            raise PresentationContentPlanError("invalid_detail_level")
        if not isinstance(budget_seconds, int) or isinstance(budget_seconds, bool) or budget_seconds <= 0:
            raise PresentationContentPlanError("invalid_or_exceeded_budget")
        sources = _tuple_strings(source_of_facts, "source_of_facts")
        if not sources or any(source not in _SOURCE_LABELS for source in sources):
            raise PresentationContentPlanError("invalid_fact_source")
        if not evidence_available:
            raise PresentationContentPlanError("evidence_missing")
        required, defaults_optional = _SCENE_SECTIONS[scene_kind]
        optional = _tuple_strings(optional_sections, "optional_sections") if optional_sections is not None else defaults_optional
        if any(section not in defaults_optional for section in optional):
            raise PresentationContentPlanError("invalid_optional_section")
        tasks = (("low_pressure_observation",) if scene_kind == "stop_guidance" else ()) if observation_tasks is None else _tuple_strings(observation_tasks, "observation_tasks")
        if role_mode == "listen_only":
            tasks = ()
            optional = tuple(section for section in optional if section != "follow_up_options")
        if scene_kind != "stop_guidance" and tasks:
            raise PresentationContentPlanError("observation_task_outside_stop_guidance")
        safety = list(_BASE_SAFETY)
        if scene_kind in {"stop_guidance", "navigation"}:
            safety.append("preserve_spatial_and_object_safety")
        if scene_kind == "tour_closing":
            safety.append("do_not_claim_unrecorded_completion")
        evidence = ["approved_facts_only", "source_boundary_preserved"]
        if scene_kind in {"stop_guidance", "navigation"}:
            evidence.append("reviewed_spatial_or_stop_context")
        goal = {
            "route_planning": "organize_a_reviewed_route_with_budget_and_next_action",
            "route_opening": "orient_the_visitor_to_the_selected_route",
            "stop_guidance": "organize_reviewed_point_facts_and_observation",
            "navigation": "guide_between_reviewed_stops_without_replanning",
            "tour_closing": "summarize_recorded_visit_without_inference",
        }[scene_kind]
        return PresentationContentPlan(
            schema_version=PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION, scene_kind=scene_kind, role_mode=role_mode,
            detail_level=detail_level, content_goal=goal, required_sections=required, optional_sections=optional,
            observation_tasks=tasks, safety_requirements=tuple(safety), evidence_requirements=tuple(evidence),
            budget_seconds=budget_seconds, fallback_mode="legacy_chain", source_of_facts=sources,
        )
    except PresentationContentPlanError as exc:
        return _rejected(str(exc), scene_kind=scene_kind, role_mode=role_mode)


_PLAN_FIELDS = frozenset(PresentationContentPlan.__dataclass_fields__)


def presentation_content_plan_from_dict(value: Mapping[str, Any] | None) -> PresentationContentPlan:
    """Strictly parse a plan and reject unknown fields or wrong types."""
    if not isinstance(value, Mapping):
        raise PresentationContentPlanError("plan_must_be_mapping")
    if set(value) - _PLAN_FIELDS:
        raise PresentationContentPlanError("unknown_plan_fields")
    if value.get("schema_version") != PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION:
        raise PresentationContentPlanError("unknown_plan_version")
    required = ("scene_kind", "role_mode", "detail_level", "content_goal", "required_sections", "optional_sections", "observation_tasks", "safety_requirements", "evidence_requirements", "budget_seconds", "fallback_mode", "source_of_facts")
    if any(field not in value for field in required):
        raise PresentationContentPlanError("missing_plan_field")
    if any(not isinstance(value[field], (list, tuple)) for field in required if field.endswith("sections") or field.endswith("tasks") or field.endswith("requirements") or field == "source_of_facts"):
        raise PresentationContentPlanError("plan_list_field_type_error")
    for field in ("schema_version", "scene_kind", "role_mode", "detail_level", "content_goal", "fallback_mode", "status"):
        if not isinstance(value.get(field), str):
            raise PresentationContentPlanError("plan_string_field_type_error")
    if not isinstance(value.get("budget_seconds"), int) or isinstance(value.get("budget_seconds"), bool):
        raise PresentationContentPlanError("budget_field_type_error")
    for field in ("reason_codes", "state_writes"):
        if field in value and not isinstance(value[field], (list, tuple)):
            raise PresentationContentPlanError("plan_audit_list_type_error")
    if "legacy_message_preserved" in value and not isinstance(value["legacy_message_preserved"], bool):
        raise PresentationContentPlanError("legacy_message_preserved_must_be_bool")
    plan = PresentationContentPlan(
        schema_version=value["schema_version"], scene_kind=value["scene_kind"], role_mode=value["role_mode"], detail_level=value["detail_level"], content_goal=value["content_goal"],
        required_sections=tuple(value["required_sections"]), optional_sections=tuple(value["optional_sections"]), observation_tasks=tuple(value["observation_tasks"]), safety_requirements=tuple(value["safety_requirements"]), evidence_requirements=tuple(value["evidence_requirements"]), budget_seconds=value["budget_seconds"], fallback_mode=value["fallback_mode"], source_of_facts=tuple(value["source_of_facts"]), status=value.get("status", "accepted"), reason_codes=tuple(value.get("reason_codes", ())), state_writes=tuple(value.get("state_writes", ())), legacy_message_preserved=value.get("legacy_message_preserved", True),
    )
    if plan.status != "accepted":
        return plan
    rebuilt = build_presentation_content_plan(scene_kind=plan.scene_kind, role_mode=plan.role_mode, detail_level=plan.detail_level, budget_seconds=plan.budget_seconds, source_of_facts=plan.source_of_facts, observation_tasks=plan.observation_tasks, optional_sections=plan.optional_sections)
    if rebuilt.status != "accepted" or rebuilt.to_dict() != plan.to_dict():
        raise PresentationContentPlanError("plan_contract_validation_failed")
    if _contains_internal_marker(plan.to_dict()) or plan.state_writes:
        raise PresentationContentPlanError("internal_field_or_state_write")
    return plan


__all__ = ["DETAIL_LEVELS", "FALLBACK_MODES", "PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION", "PresentationContentPlan", "PresentationContentPlanError", "ROLE_MODE_IDS", "SCENE_KINDS", "build_presentation_content_plan", "presentation_content_plan_from_dict"]
