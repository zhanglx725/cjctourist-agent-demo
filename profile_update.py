"""Deterministic C4 preference updates for an already active guided tour.

This adapter owns no natural-language model and never mutates its inputs.  It
uses C2 only to recognize the same supported preference vocabulary, C1 to
validate an immutable new profile, A1's event adapter for time replanning, and
TourState's narrow snapshot transition for interests/detail level.
"""

from __future__ import annotations

import re
from typing import Any

from profile_dialogue import extract_profile_patch
from tour_interaction import handle_tour_event
from tour_state import TourStateError, apply_profile_snapshot
from visitor_profile import (
    VisitorProfileError,
    create_visitor_profile,
    profile_from_dict,
    update_visitor_profile,
)


TIME_UPDATE_RE = re.compile(r"(?:只剩|还剩|剩余)\s*\d{1,3}\s*分钟")
INTEREST_UPDATE_CUES = ("接下来", "后面", "之后", "想多看", "更想", "改看", "更喜欢")
DETAIL_UPDATE_CUES = ("后面", "接下来", "之后", "简单讲", "详细一点", "深入一点", "想听深入", "想深入")


def _is_update_text(text: str, fields: set[str]) -> bool:
    """Require explicit change language so point questions stay in A2 RAG."""
    if "available_minutes" in fields and TIME_UPDATE_RE.search(text):
        return True
    if "interests" in fields and any(cue in text for cue in INTEREST_UPDATE_CUES):
        return True
    if "detail_level" in fields and any(cue in text for cue in DETAIL_UPDATE_CUES):
        return True
    return False


def is_profile_update_request(text: str) -> bool:
    """Return whether a text is an explicit C4 update, without changing state."""
    patch, fields, conflict = extract_profile_patch(text)
    if conflict:
        # A conflicting phrase still belongs to C4 when it explicitly tries
        # to alter time, interests, or depth; the adapter will reject it.
        return bool(TIME_UPDATE_RE.search(text) or any(cue in text for cue in (*INTEREST_UPDATE_CUES, *DETAIL_UPDATE_CUES)))
    return bool(patch) and _is_update_text(text, fields)


def _base_profile(
    visitor_profile: dict[str, Any] | None,
    tour_state: dict[str, Any],
):
    """Prefer the C3 profile; safely reconstruct one for legacy live tours."""
    if visitor_profile:
        return profile_from_dict(visitor_profile)
    return create_visitor_profile(
        available_minutes=tour_state["available_minutes"],
        interests=tour_state["interests"],
        detail_level=tour_state["detail_level"],
    )


def _result(
    *,
    ok: bool,
    code: str,
    message: str,
    visitor_profile: dict[str, Any] | None,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "code": code,
        "message": message,
        "visitor_profile": visitor_profile,
        "tour_state": tour_state,
        "interaction_state": interaction_state,
        "data": data or {},
    }


def apply_profile_update(
    visitor_profile_data: dict[str, Any] | None,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    user_text: str,
) -> dict[str, Any]:
    """Apply one all-or-nothing C4 update to an active tour.

    A time change is validated *before* `replan_time` runs.  Only when the
    existing deterministic replan succeeds does this adapter save the new
    VisitorProfile and TourState snapshot.  Interest/depth changes leave the
    reviewed route untouched and only affect future StopPrograms.
    """
    if not tour_state or not interaction_state:
        return _result(
            ok=False, code="route_not_initialized", message="请先建立游览路线，再调整导览偏好。",
            visitor_profile=visitor_profile_data, tour_state=tour_state,
            interaction_state=interaction_state,
        )
    patch, fields, conflict = extract_profile_patch(user_text)
    if conflict:
        return _result(
            ok=False, code="conflicting_profile_values", message=conflict,
            visitor_profile=visitor_profile_data, tour_state=tour_state,
            interaction_state=interaction_state,
        )
    if not patch or not _is_update_text(user_text, fields):
        return _result(
            ok=False, code="profile_update_unresolved",
            message="请明确说明要调整的剩余时间、兴趣或讲解深度。",
            visitor_profile=visitor_profile_data, tour_state=tour_state,
            interaction_state=interaction_state,
        )
    try:
        current_profile = _base_profile(visitor_profile_data, tour_state)
        updated_profile = update_visitor_profile(current_profile, **patch)
    except VisitorProfileError as exc:
        return _result(
            ok=False, code="invalid_profile_update", message=f"偏好更新无效：{exc}",
            visitor_profile=visitor_profile_data, tour_state=tour_state,
            interaction_state=interaction_state,
        )

    updated_tour = tour_state
    updated_interaction = interaction_state
    data: dict[str, Any] = {}
    if "available_minutes" in patch:
        replan = handle_tour_event(
            tour_state, interaction_state, "replan_time",
            available_minutes=updated_profile.available_minutes,
        )
        if not replan["ok"]:
            return _result(
                ok=False, code=f"replan_{replan['code']}", message=replan["message"],
                visitor_profile=visitor_profile_data, tour_state=tour_state,
                interaction_state=interaction_state,
            )
        updated_tour = replan["tour_state"]
        updated_interaction = replan["interaction_state"]
        data = dict(replan.get("data") or {})

    try:
        updated_tour = apply_profile_snapshot(
            updated_tour,
            available_minutes=updated_profile.available_minutes,
            interests=list(updated_profile.interests),
            detail_level=updated_profile.detail_level,
        )
    except TourStateError as exc:
        # This is defensive.  The original inputs are preserved even if a
        # future TourState invariant rejects a valid C1 profile.
        return _result(
            ok=False, code="snapshot_rejected", message=f"无法同步本次导览偏好：{exc}",
            visitor_profile=visitor_profile_data, tour_state=tour_state,
            interaction_state=interaction_state,
        )

    changed = "、".join(
        {"available_minutes": "剩余时间", "interests": "讲解兴趣", "detail_level": "讲解深度"}[field]
        for field in ("available_minutes", "interests", "detail_level") if field in fields
    )
    code = "profile_replanned" if "available_minutes" in patch else "profile_updated"
    return _result(
        ok=True, code=code, message=f"已更新{changed}；后续导览将按新的偏好继续。",
        visitor_profile=updated_profile.to_dict(), tour_state=updated_tour,
        interaction_state=updated_interaction, data=data,
    )
