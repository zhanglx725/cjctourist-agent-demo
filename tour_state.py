"""Pure session-memory transitions for a Chen Clan Academy guided tour.

This module has no LangGraph or LLM dependency.  Every function returns a new
state dictionary and never mutates the caller's state, which makes the first
TourState phase straightforward to test and safe to reuse in graph nodes.
"""

from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NODES_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")
ENTRY_NODE_ID = "entrance_main_outside"
VALID_DETAIL_LEVELS = {"short", "standard", "deep"}
VALID_ROUTE_STATUSES = {"not_started", "touring", "completed", "replanning"}


class TourStateError(ValueError):
    """Raised when a TourState transition violates reviewed route data."""


def known_node_ids(nodes_file: Path = NODES_FILE) -> set[str]:
    """Load the authoritative IDs from the human-reviewed marker inventory."""
    with nodes_file.open(encoding="utf-8-sig", newline="") as handle:
        return {row["node_id"] for row in csv.DictReader(handle) if row.get("node_id")}


def _plan_stop_ids(plan: Any) -> list[str]:
    """Extract formal guide stops from static or dynamic route-plan objects."""
    raw_ids = list(getattr(plan, "stop_ids", ()))
    return [node_id for node_id in raw_ids if node_id != ENTRY_NODE_ID]


def _plan_id(plan: Any) -> str:
    if hasattr(plan, "route_id"):
        return str(plan.route_id)
    if hasattr(plan, "requested_minutes"):
        return f"dynamic_{plan.requested_minutes}"
    raise TourStateError("路线计划缺少 route_id 或 requested_minutes。")


def _plan_minutes(plan: Any) -> int:
    value = getattr(plan, "target_minutes", getattr(plan, "requested_minutes", None))
    if value is None:
        raise TourStateError("路线计划缺少目标时间。")
    return int(value)


def _copy_state(state: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(state)
    _validate_state(copied)
    return copied


def _validate_state(state: dict[str, Any]) -> None:
    required = {
        "selected_route_id", "route_stop_ids", "current_stop_id", "visited_stop_ids",
        "skipped_stop_ids", "remaining_stop_ids", "started_at", "available_minutes",
        "remaining_minutes", "interests", "detail_level", "route_status",
    }
    missing = required.difference(state)
    if missing:
        raise TourStateError(f"TourState 缺少字段：{', '.join(sorted(missing))}")
    if state["route_status"] not in VALID_ROUTE_STATUSES:
        raise TourStateError(f"未知路线状态：{state['route_status']}")
    if state["detail_level"] not in VALID_DETAIL_LEVELS:
        raise TourStateError(f"未知讲解详略等级：{state['detail_level']}")
    route = list(state["route_stop_ids"])
    visited = list(state["visited_stop_ids"])
    skipped = list(state["skipped_stop_ids"])
    remaining = list(state["remaining_stop_ids"])
    unknown = set(route + visited + skipped + remaining).difference(known_node_ids())
    if unknown:
        raise TourStateError(f"TourState 含不在 marker_inventory_v0.csv 的点位：{', '.join(sorted(unknown))}")
    if len(route) != len(set(route)):
        raise TourStateError("正式讲解点不能重复。")
    if set(visited).intersection(skipped):
        raise TourStateError("已访问点与跳过点不能交叉。")
    if set(remaining).intersection(visited) or set(remaining).intersection(skipped):
        raise TourStateError("剩余点不能与已访问点或跳过点交叉。")
    if set(visited + skipped + remaining) != set(route):
        raise TourStateError("已访问、跳过和剩余点必须完整覆盖当前路线正式讲解点。")
    if state["current_stop_id"] is not None and state["current_stop_id"] not in known_node_ids():
        raise TourStateError(f"当前点位不在 marker_inventory_v0.csv：{state['current_stop_id']}")


def start_tour(
    plan: Any,
    interests: list[str] | None = None,
    detail_level: str = "standard",
) -> dict[str, Any]:
    """Create a new in-memory tour from an already-reviewed route plan."""
    if detail_level not in VALID_DETAIL_LEVELS:
        raise TourStateError(f"detail_level 必须为：{', '.join(sorted(VALID_DETAIL_LEVELS))}")
    stops = _plan_stop_ids(plan)
    if not stops:
        raise TourStateError("路线计划没有正式讲解点。")
    unknown = set(stops).difference(known_node_ids())
    if unknown:
        raise TourStateError(f"路线含未知点位：{', '.join(sorted(unknown))}")
    minutes = _plan_minutes(plan)
    return {
        "selected_route_id": _plan_id(plan),
        "route_stop_ids": stops,
        "current_stop_id": None,
        "visited_stop_ids": [],
        "skipped_stop_ids": [],
        "remaining_stop_ids": list(stops),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "available_minutes": minutes,
        "remaining_minutes": minutes,
        "interests": list(interests or []),
        "detail_level": detail_level,
        "route_status": "not_started",
    }


def apply_profile_snapshot(
    state: dict[str, Any],
    *,
    available_minutes: int,
    interests: list[str],
    detail_level: str,
) -> dict[str, Any]:
    """Apply an already C1-validated C-stage preference snapshot immutably.

    It never alters formal stops, visited/skipped records, current position or
    route status.  Time replanning itself remains the responsibility of the
    A1 `replan_time` adapter; C4 invokes this only after that operation has
    succeeded, so profile and execution state stay atomic.
    """
    snapshot = _copy_state(state)
    if isinstance(available_minutes, bool) or not isinstance(available_minutes, int):
        raise TourStateError("画像快照的 available_minutes 必须是整数。")
    if available_minutes <= 0:
        raise TourStateError("画像快照的 available_minutes 必须大于 0。")
    if not isinstance(interests, list) or not all(isinstance(item, str) for item in interests):
        raise TourStateError("画像快照的 interests 必须是字符串列表。")
    if detail_level not in VALID_DETAIL_LEVELS:
        raise TourStateError("画像快照的 detail_level 无效。")
    snapshot["available_minutes"] = available_minutes
    snapshot["interests"] = list(interests)
    snapshot["detail_level"] = detail_level
    _validate_state(snapshot)
    return snapshot


def next_stop(state: dict[str, Any]) -> str | None:
    """Return the next formal, unvisited and unskipped guide stop in route order."""
    snapshot = _copy_state(state)
    return snapshot["remaining_stop_ids"][0] if snapshot["remaining_stop_ids"] else None


def _record_arrival(
    state: dict[str, Any], node_id: str, arrival_kind: str
) -> dict[str, Any]:
    """Record location only; A1 completion is handled by the interaction layer.

    This is deliberately private.  ``tour_interaction.py`` is the public event
    adapter and decides whether an arrival is planned or self-directed.  An
    arrival must never be treated as a completed explanation.
    """
    snapshot = _copy_state(state)
    if node_id not in known_node_ids():
        raise TourStateError(f"未知点位：{node_id}")
    snapshot["current_stop_id"] = node_id
    snapshot["last_arrival_kind"] = arrival_kind
    if snapshot["route_status"] == "not_started":
        snapshot["route_status"] = "touring"
    _validate_state(snapshot)
    return snapshot


def _complete_current_stop(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Move one explicitly confirmed formal stop from remaining to visited.

    This private primitive intentionally has no UI/LLM behavior.  The adapter
    has already verified the current station, pending station and interaction
    phase before it calls this function.
    """
    snapshot = _copy_state(state)
    if node_id not in snapshot["remaining_stop_ids"]:
        raise TourStateError("只能确认当前路线中尚未完成的正式讲解点。")
    snapshot["remaining_stop_ids"].remove(node_id)
    snapshot["visited_stop_ids"].append(node_id)
    snapshot["route_status"] = "completed" if not snapshot["remaining_stop_ids"] else "touring"
    _validate_state(snapshot)
    return snapshot


def skip_stop(state: dict[str, Any], node_id: str | None = None) -> dict[str, Any]:
    """Skip an explicit remaining stop, or the currently recommended next stop."""
    snapshot = _copy_state(state)
    target = node_id or next_stop(snapshot)
    if target is None:
        raise TourStateError("当前没有可跳过的剩余讲解点。")
    if target not in snapshot["remaining_stop_ids"]:
        raise TourStateError("只能跳过当前路线中尚未完成的正式讲解点。")
    snapshot["remaining_stop_ids"].remove(target)
    snapshot["skipped_stop_ids"].append(target)
    snapshot["route_status"] = "completed" if not snapshot["remaining_stop_ids"] else "touring"
    _validate_state(snapshot)
    return snapshot


def finish_tour(state: dict[str, Any]) -> dict[str, Any]:
    """Explicitly close the session while retaining real visited/skipped records."""
    snapshot = _copy_state(state)
    snapshot["route_status"] = "completed"
    snapshot["completion_reason"] = (
        "all_stops_processed" if not snapshot["remaining_stop_ids"] else "visitor_finished_early"
    )
    return snapshot


def apply_replanned_route(
    state: dict[str, Any],
    remaining_stop_ids: list[str],
    remaining_minutes: int,
    selected_route_id: str | None = None,
    preserve_current_stop: bool = False,
) -> dict[str, Any]:
    """Replace only the unfinished portion after deterministic replanning."""
    snapshot = _copy_state(state)
    if remaining_minutes <= 0:
        raise TourStateError("剩余时间必须大于 0。")
    unknown = set(remaining_stop_ids).difference(known_node_ids())
    if unknown:
        raise TourStateError(f"重规划含未知点位：{', '.join(sorted(unknown))}")
    forbidden = set(snapshot["visited_stop_ids"]).union(snapshot["skipped_stop_ids"])
    if forbidden.intersection(remaining_stop_ids):
        raise TourStateError("重规划不能重新加入已访问或已跳过的点位。")
    old_remaining = list(snapshot["remaining_stop_ids"])
    current = snapshot["current_stop_id"]
    preserved_current = (
        current
        if preserve_current_stop and current is not None and current in old_remaining
        else None
    )
    effective_remaining = [
        *([preserved_current] if preserved_current else []),
        *[node_id for node_id in remaining_stop_ids if node_id != preserved_current],
    ]
    if len(effective_remaining) != len(set(effective_remaining)):
        raise TourStateError("重规划后的剩余讲解点不能重复。")
    snapshot["replanned_out_stop_ids"] = [
        node_id for node_id in old_remaining if node_id not in effective_remaining
    ]
    snapshot["route_stop_ids"] = [
        *snapshot["visited_stop_ids"],
        *snapshot["skipped_stop_ids"],
        *effective_remaining,
    ]
    snapshot["remaining_stop_ids"] = effective_remaining
    snapshot["remaining_minutes"] = int(remaining_minutes)
    if selected_route_id:
        snapshot["selected_route_id"] = selected_route_id
    snapshot["route_status"] = "completed" if not effective_remaining else "touring"
    _validate_state(snapshot)
    return snapshot
