"""Deterministic, route-aware triggering for optional photo-pose guidance.

The trigger plan is session presentation state only.  It must never mutate the
formal route, TourState, VisitorProfile, or NarrationCoverage.  A card can be
shown only on the first arrival at a planned, editorially eligible stop.
"""

from __future__ import annotations

from copy import deepcopy
from math import ceil
from typing import Any, Callable

from photo_spot_validation import query_available_photo_spots


SCHEMA_VERSION = "proactive_photo_guidance_v1"


def _time_cap(minutes: int) -> int:
    if minutes < 30:
        return 1
    if minutes < 60:
        return 2
    return 3


def _distributed(items: list[str], count: int) -> list[str]:
    """Choose stable positions across the route instead of front-loading tips."""
    if count <= 0:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    indices = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    return [items[index] for index in indices]


def build_photo_trigger_plan(
    tour_state: dict[str, Any] | None,
    *,
    selector: Callable[..., dict[str, Any]] = query_available_photo_spots,
) -> dict[str, Any]:
    tour = tour_state or {}
    route = [str(item) for item in tour.get("route_stop_ids", []) if item]
    minutes = max(0, int(tour.get("available_minutes") or 0))
    eligible: list[str] = []
    for node_id in route:
        try:
            if selector(node_id=node_id).get("available"):
                eligible.append(node_id)
        except Exception:
            # Optional guidance must fail closed without interrupting the tour.
            continue
    route_cap = max(1, ceil(len(route) / 2)) if route else 0
    max_count = min(_time_cap(minutes), route_cap, len(eligible))
    return {
        "schema_version": SCHEMA_VERSION,
        "route_id": tour.get("selected_route_id"),
        "available_minutes": minutes,
        "route_stop_ids": route,
        "max_count": max_count,
        "planned_stop_ids": _distributed(eligible, max_count),
        "triggered_stop_ids": [],
    }


def _render(selection: dict[str, Any]) -> str:
    spot = selection.get("photo_spot") or {}
    title = str(spot.get("title_zh") or "这个位置").strip()
    lines = [f"【打卡姿势建议】{title}"]
    poses = selection.get("pose_templates") or []
    if poses and str(poses[0].get("instruction_zh") or "").strip():
        lines.append(str(poses[0]["instruction_zh"]).strip())
    boundaries: list[str] = []
    for item in selection.get("limitations") or []:
        text = str(item or "").strip()
        if not text or "draft_manual_review" in text or text.startswith("原卡为"):
            continue
        if text not in boundaries:
            boundaries.append(text)
    lines.extend(boundaries)
    return "\n".join(lines)


def maybe_trigger_photo_guidance(
    *,
    tour_state: dict[str, Any] | None,
    existing_plan: dict[str, Any] | None,
    last_tour_event: dict[str, Any] | None,
    visitor_profile: dict[str, Any] | None,
    detailed: bool,
    selector: Callable[..., dict[str, Any]] = query_available_photo_spots,
) -> dict[str, Any]:
    """Return an optional public card and an updated isolated trigger plan."""
    tour = tour_state or {}
    event = last_tour_event or {}
    profile = visitor_profile or {}
    plan = deepcopy(existing_plan) if isinstance(existing_plan, dict) else None
    if not plan or plan.get("route_id") != tour.get("selected_route_id"):
        plan = build_photo_trigger_plan(tour, selector=selector)

    node_id = tour.get("current_stop_id")
    blocked = (
        detailed
        or event.get("event") != "arrive_at_stop"
        or not event.get("ok", False)
        or profile.get("interaction_mode") == "listen_only"
        or profile.get("explanation_style") == "listen_only"
        or not node_id
        or node_id not in plan.get("planned_stop_ids", [])
        or node_id in plan.get("triggered_stop_ids", [])
        or len(plan.get("triggered_stop_ids", [])) >= int(plan.get("max_count") or 0)
    )
    if blocked:
        return {"triggered": False, "message": None, "plan": plan}

    try:
        selection = selector(node_id=node_id)
    except Exception:
        return {"triggered": False, "message": None, "plan": plan}
    if not selection.get("available"):
        return {"triggered": False, "message": None, "plan": plan}
    plan["triggered_stop_ids"] = [*plan.get("triggered_stop_ids", []), node_id]
    return {
        "triggered": True,
        "message": _render(selection),
        "plan": plan,
        "photo_spot_id": (selection.get("photo_spot") or {}).get("photo_spot_id"),
    }
