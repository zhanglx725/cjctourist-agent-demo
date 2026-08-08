"""Read-only role-text candidates for route planning and route opening.

The legacy route and opening messages remain the authoritative public text.
This module deliberately creates a bounded *candidate* by adding only a
reviewed style lead-in before the complete legacy message.  Keeping the legacy
message verbatim inside every accepted candidate gives the validator a strong
fact, route, and safety boundary without exposing route IDs or evidence IDs.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from controlled_knowledge_query import public_visitor_message_or_fallback
from presentation_content_plan import PresentationContentPlan, presentation_content_plan_from_dict


ROUTE_ROLE_TEXT_CANDIDATE_SCHEMA_VERSION = "route_role_text_candidate_v1"
SCENE_KINDS = frozenset({"route_planning", "route_opening"})
ROLE_MODES = frozenset({"standard", "ancient_scholar", "child", "listen_only"})
_CANDIDATE_FIELDS = frozenset({"schema_version", "scene_kind", "role_mode", "public_text"})
_INTERNAL = re.compile(
    r"(?:https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|node[_ ]?id|route[_ ]?id|"
    r"object[_ ]?id|raw[_ ]?chunk|rag_tool|llm_think|tourstate|visitorprofile)",
    re.IGNORECASE,
)
_STYLE_PREFIX = {
    "standard": "",
    "ancient_scholar": "请随我循既定行程，从容观览。\n\n",
    "child": "我们按已经安排好的路线，一站一站慢慢看。\n\n",
    "listen_only": "以下为本次行程安排。\n\n",
}


def _visible_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def _rejected_record(
    *,
    scene_kind: str,
    role_mode: str,
    legacy_text: str,
    reason_codes: list[str],
    candidate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scene_kind": scene_kind,
        "role_mode": role_mode,
        "candidate_status": "rejected",
        "validation_status": "rejected",
        "fallback_reason": reason_codes[0] if reason_codes else "candidate_rejected",
        "reason_codes": reason_codes,
        "candidate": dict(candidate) if isinstance(candidate, Mapping) else None,
        "legacy_message_present": bool(legacy_text),
        "legacy_message_preserved": True,
        "candidate_is_non_authoritative": True,
        "state_writes": [],
        "fact_diff": ["legacy_message_not_preserved"] if legacy_text else ["legacy_message_unavailable"],
        "route_diff": ["legacy_message_not_preserved"] if legacy_text else ["legacy_message_unavailable"],
        "safety_diff": ["legacy_message_not_preserved"] if legacy_text else ["legacy_message_unavailable"],
        "public_output_safe": False,
        "role_consistent": False,
        "budget_consistent": False,
    }


def build_route_role_text_candidate(
    *, scene_kind: str, role_mode: str, legacy_text: str
) -> dict[str, Any]:
    """Build a closed candidate envelope without calling a model or tools."""
    return {
        "schema_version": ROUTE_ROLE_TEXT_CANDIDATE_SCHEMA_VERSION,
        "scene_kind": scene_kind,
        "role_mode": role_mode,
        "public_text": f"{_STYLE_PREFIX.get(role_mode, '')}{legacy_text}",
    }


def validate_route_role_text_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    plan: PresentationContentPlan | Mapping[str, Any] | None,
    legacy_text: str,
) -> dict[str, Any]:
    """Fail closed unless a candidate is an exact safe restyling of legacy text."""
    scene_kind = "unknown"
    role_mode = "standard"
    if isinstance(plan, Mapping):
        scene_kind = str(plan.get("scene_kind") or scene_kind)
        role_mode = str(plan.get("role_mode") or role_mode)
    elif isinstance(plan, PresentationContentPlan):
        scene_kind, role_mode = plan.scene_kind, plan.role_mode
    try:
        parsed_plan = (
            plan if isinstance(plan, PresentationContentPlan)
            else presentation_content_plan_from_dict(plan)  # type: ignore[arg-type]
        )
    except Exception:
        return _rejected_record(
            scene_kind=scene_kind, role_mode=role_mode, legacy_text=legacy_text,
            reason_codes=["presentation_plan_unavailable"], candidate=candidate,
        )
    scene_kind, role_mode = parsed_plan.scene_kind, parsed_plan.role_mode
    if parsed_plan.status != "accepted" or scene_kind not in SCENE_KINDS:
        return _rejected_record(
            scene_kind=scene_kind, role_mode=role_mode, legacy_text=legacy_text,
            reason_codes=["unsupported_or_rejected_presentation_plan"], candidate=candidate,
        )
    if not legacy_text:
        return _rejected_record(
            scene_kind=scene_kind, role_mode=role_mode, legacy_text=legacy_text,
            reason_codes=["legacy_message_unavailable"], candidate=candidate,
        )
    reasons: list[str] = []
    if not isinstance(candidate, Mapping) or frozenset(candidate) != _CANDIDATE_FIELDS:
        reasons.append("invalid_candidate_schema")
        candidate_text = ""
    else:
        candidate_text = candidate.get("public_text")
        if (
            candidate.get("schema_version") != ROUTE_ROLE_TEXT_CANDIDATE_SCHEMA_VERSION
            or candidate.get("scene_kind") != scene_kind
            or candidate.get("role_mode") != role_mode
            or not isinstance(candidate_text, str)
        ):
            reasons.append("invalid_candidate_fields")
        candidate_text = candidate_text if isinstance(candidate_text, str) else ""
    expected_text = f"{_STYLE_PREFIX.get(role_mode, '')}{legacy_text}"
    if role_mode not in ROLE_MODES:
        reasons.append("invalid_role_mode")
    if candidate_text != expected_text:
        reasons.append("legacy_boundary_or_role_template_mismatch")
    if _INTERNAL.search(candidate_text):
        reasons.append("internal_field_leak")
    if public_visitor_message_or_fallback(candidate_text) != candidate_text:
        reasons.append("public_message_boundary_rejected")
    if role_mode == "listen_only" and re.search(r"[?？]|(?:请你|请问|回答|任务|拍照)", candidate_text):
        reasons.append("listen_only_interaction_violation")
    within_budget = (
        parsed_plan.budget_seconds > 0
        and _visible_length(candidate_text) <= parsed_plan.budget_seconds * 4
    )
    if not within_budget:
        reasons.append("content_budget_exceeded")
    fact_boundary_ok = candidate_text == expected_text
    public_safe = not bool(_INTERNAL.search(candidate_text)) and (
        public_visitor_message_or_fallback(candidate_text) == candidate_text
    )
    role_consistent = not any(
        reason in reasons for reason in (
            "invalid_role_mode", "legacy_boundary_or_role_template_mismatch",
            "listen_only_interaction_violation",
        )
    )
    if reasons:
        return _rejected_record(
            scene_kind=scene_kind, role_mode=role_mode, legacy_text=legacy_text,
            reason_codes=list(dict.fromkeys(reasons)), candidate=candidate,
        )
    return {
        "scene_kind": scene_kind,
        "role_mode": role_mode,
        "candidate_status": "generated",
        "validation_status": "accepted",
        "fallback_reason": None,
        "reason_codes": [],
        "candidate": dict(candidate),
        "legacy_message_present": True,
        "legacy_message_preserved": True,
        "candidate_is_non_authoritative": True,
        "state_writes": [],
        "fact_diff": [] if fact_boundary_ok else ["legacy_message_not_preserved"],
        "route_diff": [] if fact_boundary_ok else ["legacy_message_not_preserved"],
        "safety_diff": [] if fact_boundary_ok else ["legacy_message_not_preserved"],
        "public_output_safe": public_safe,
        "role_consistent": role_consistent,
        "budget_consistent": within_budget,
    }


__all__ = [
    "ROUTE_ROLE_TEXT_CANDIDATE_SCHEMA_VERSION",
    "build_route_role_text_candidate",
    "validate_route_role_text_candidate",
]
