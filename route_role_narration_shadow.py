"""Read-only role-text candidates for route and navigation surfaces.

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
SCENE_KINDS = frozenset({
    "route_planning", "route_opening", "navigation", "tour_closing",
})
ROLE_MODES = frozenset({
    "standard", "neutral", "child", "family", "student_research", "professional",
    "listen_only", "mixed_group", "dominant_ceo", "cute_junior", "ancient_scholar",
    "warm_sister", "bestie_chat", "buddy_guide", "exploration_game", "photo_guide",
    "hostel_scholar", "xiguan_young_master", "cantonese_storyteller",
})
_CANDIDATE_FIELDS = frozenset({"schema_version", "scene_kind", "role_mode", "public_text"})
_INTERNAL = re.compile(
    r"(?:https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|node[_ ]?id|route[_ ]?id|"
    r"object[_ ]?id|raw[_ ]?chunk|rag_tool|llm_think|tourstate|visitorprofile)",
    re.IGNORECASE,
)
_STYLE_PREFIX = {
    "route_planning": {
        "standard": "",
        "ancient_scholar": (
            "今日且把这段行程当作一卷徐徐展开的图景。路线、时长与先后次序"
            "都已排定，诸位随我依次观来。\n\n"
        ),
        "child": "我们按已经安排好的路线，一站一站慢慢看。\n\n",
        "listen_only": "以下为本次行程安排。\n\n",
    },
    "route_opening": {
        "standard": "",
        "ancient_scholar": (
            "诸位，行程既定，便从眼前第一站启程。一路不必匆忙，且看构件、"
            "辨工艺，再把沿途细节一一串起。\n\n"
        ),
        "child": "我们按已经安排好的路线，一站一站慢慢看。\n\n",
        "listen_only": "以下为本次行程安排。\n\n",
    },
    "navigation": {
        "standard": "",
        "ancient_scholar": "前路已明，请随我依照既定路线移步。\n\n",
        "child": "下一段路线已经安排好了，我们按提示慢慢前往。\n\n",
        "listen_only": "以下是前往下一站的路线提示。\n\n",
    },
    "tour_closing": {
        "standard": "",
        "ancient_scholar": "此行所见，且容我为您作一番收束。\n\n",
        "child": "今天的探索告一段落，我们来看看这次旅程留下了什么。\n\n",
        "listen_only": "以下是本次游览的结束记录。\n\n",
    },
}

# Route surfaces retain every deterministic route fact verbatim.  These short
# lead-ins make the selected role visible without giving a model authority
# over route order, timing, safety or state.
_ROUTE_ROLE_OPENINGS = {
    "neutral": "我们按既定安排开始这一段行程。\n\n",
    "family": "我们慢慢走，把这一段行程照顾得从容些。\n\n",
    "student_research": "先带着一个观察问题进入这段路线。\n\n",
    "professional": "先明确行程结构，再依次查看重点。\n\n",
    "mixed_group": "大家可按自己的节奏跟随这段安排。\n\n",
    "dominant_ceo": "重点已定，直接进入行程。\n\n",
    "cute_junior": "先看这一段的亮点，行程马上开始。\n\n",
    "warm_sister": "不着急，我们按安排慢慢走。\n\n",
    "bestie_chat": "这段行程有几个细节，咱们边走边看。\n\n",
    "buddy_guide": "咱们抓重点，按安排往下走。\n\n",
    "exploration_game": "这一段的线索已经排好，慢慢找。\n\n",
    "photo_guide": "先把行程走稳，画面重点沿途再看。\n\n",
    "hostel_scholar": "行至此处，先按次序展开这段行程。\n\n",
    "xiguan_young_master": "得闲就照这段安排慢慢行。\n\n",
    "cantonese_storyteller": "话说眼前这段行程，就从第一站讲起。\n\n",
}


def _style_prefix(scene_kind: str, role_mode: str) -> str:
    prefix = _STYLE_PREFIX.get(scene_kind, {}).get(role_mode)
    if prefix is not None:
        return prefix
    if scene_kind in {"route_planning", "route_opening"}:
        return _ROUTE_ROLE_OPENINGS.get(role_mode, "")
    return ""


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
        "public_text": f"{_style_prefix(scene_kind, role_mode)}{legacy_text}",
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
    expected_text = f"{_style_prefix(scene_kind, role_mode)}{legacy_text}"
    if role_mode not in ROLE_MODES:
        reasons.append("invalid_role_mode")
    if candidate_text != expected_text:
        reasons.append("legacy_boundary_or_role_template_mismatch")
    if _INTERNAL.search(candidate_text):
        reasons.append("internal_field_leak")
    if public_visitor_message_or_fallback(candidate_text) != candidate_text:
        reasons.append("public_message_boundary_rejected")
    # The legacy message remains authoritative and can contain an existing
    # product follow-up.  listen_only forbids the role layer from *adding* a
    # question/task; it must not reject an unchanged legacy prompt.
    added_role_text = (
        candidate_text.replace(legacy_text, "", 1)
        if legacy_text and legacy_text in candidate_text
        else candidate_text
    )
    if role_mode == "listen_only" and re.search(
        r"[?？]|(?:请你|请问|回答|任务|拍照)", added_role_text,
    ):
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


def _validate_route_scene_candidate(
    expected_scene: str,
    candidate: Mapping[str, Any] | None,
    *,
    plan: PresentationContentPlan | Mapping[str, Any] | None,
    legacy_text: str,
) -> dict[str, Any]:
    scene_kind = (
        plan.scene_kind if isinstance(plan, PresentationContentPlan)
        else str((plan or {}).get("scene_kind") or "unknown")
    )
    if scene_kind != expected_scene:
        role_mode = (
            plan.role_mode if isinstance(plan, PresentationContentPlan)
            else str((plan or {}).get("role_mode") or "standard")
        )
        return _rejected_record(
            scene_kind=scene_kind, role_mode=role_mode, legacy_text=legacy_text,
            reason_codes=[f"{expected_scene}_plan_required"], candidate=candidate,
        )
    return validate_route_role_text_candidate(
        candidate, plan=plan, legacy_text=legacy_text,
    )


def validate_navigation_role_narration(
    candidate: Mapping[str, Any] | None,
    *,
    plan: PresentationContentPlan | Mapping[str, Any] | None,
    legacy_text: str,
) -> dict[str, Any]:
    """Validate only navigation role text against its legacy route boundary."""
    return _validate_route_scene_candidate(
        "navigation", candidate, plan=plan, legacy_text=legacy_text,
    )


def validate_closing_role_narration(
    candidate: Mapping[str, Any] | None,
    *,
    plan: PresentationContentPlan | Mapping[str, Any] | None,
    legacy_text: str,
) -> dict[str, Any]:
    """Validate only closing role text against its legacy summary boundary."""
    return _validate_route_scene_candidate(
        "tour_closing", candidate, plan=plan, legacy_text=legacy_text,
    )


def validate_replan_presentation(
    candidate_text: str | None,
    *,
    legacy_text: str,
) -> dict[str, Any]:
    """Validate replan wording without granting authority over route state."""
    reasons: list[str] = []
    if not legacy_text:
        reasons.append("legacy_message_unavailable")
    if not isinstance(candidate_text, str) or candidate_text != legacy_text:
        reasons.append("legacy_replan_boundary_changed")
    public_safe = bool(candidate_text) and (
        not _INTERNAL.search(candidate_text or "")
        and public_visitor_message_or_fallback(candidate_text or "") == candidate_text
    )
    if not public_safe:
        reasons.append("public_message_boundary_rejected")
    return {
        "scene_kind": "replan_presentation",
        "validation_status": "accepted" if not reasons else "rejected",
        "reason_codes": list(dict.fromkeys(reasons)),
        "state_writes": [],
        "legacy_message_preserved": candidate_text == legacy_text,
        "route_diff": [],
        "public_output_safe": public_safe,
    }


__all__ = [
    "ROUTE_ROLE_TEXT_CANDIDATE_SCHEMA_VERSION",
    "build_route_role_text_candidate",
    "validate_closing_role_narration",
    "validate_navigation_role_narration",
    "validate_replan_presentation",
    "validate_route_role_text_candidate",
]
