"""A1 deterministic adapter for every tour interaction event.

This module is the only public entry point for modifying a live TourState
after route initialization.  It contains no LangGraph, LLM, RAG or UI code.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from replanning import replan_after_skip, replan_remaining_time
from tour_navigation import next_stop_navigation
from tour_state import (
    TourStateError,
    _complete_current_stop,
    _record_arrival,
    finish_tour as _finish_tour,
    known_node_ids,
)


VALID_TOUR_MODES = {"chat", "button_guided", "continuous"}
VALID_STOP_PHASES = {"navigating", "explaining", "awaiting_confirmation", "finished"}
EVENTS = {
    "arrive_at_stop",
    "next_stop",
    "skip_stop",
    "replan_time",
    "finish_tour",
    "request_stop_detail",
    "confirm_stop_complete",
}


def initialize_interaction(
    tour_state: dict[str, Any], tour_mode: str = "chat"
) -> dict[str, Any]:
    """Create UI-neutral interaction state for an initialized route."""
    if tour_mode not in VALID_TOUR_MODES:
        raise TourStateError(f"未知导游模式：{tour_mode}")
    remaining = tour_state.get("remaining_stop_ids", []) if tour_state else []
    pending = remaining[0] if remaining else None
    return {
        "pending_stop_id": pending,
        "tour_mode": tour_mode,
        "stop_phase": "finished" if tour_state.get("route_status") == "completed" else "navigating",
    }


def _snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return deepcopy(value) if value is not None else None


def _result(
    *,
    ok: bool,
    event: str,
    code: str,
    message: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    data: dict[str, Any] | None = None,
    idempotent: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "event": event,
        "code": code,
        "message": message,
        "tour_state": _snapshot(tour_state),
        "interaction_state": _snapshot(interaction_state),
        "data": data or {},
        "idempotent": idempotent,
    }


def _rejection(
    event: str,
    code: str,
    message: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> dict[str, Any]:
    return _result(
        ok=False,
        event=event,
        code=code,
        message=message,
        tour_state=tour_state,
        interaction_state=interaction_state,
    )


def _validate_context(
    event: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    *,
    allow_finished_idempotent: bool = False,
) -> dict[str, Any] | None:
    if tour_state is None or interaction_state is None:
        return _rejection(event, "route_not_initialized", "请先建立游览路线。", tour_state, interaction_state)
    if interaction_state.get("tour_mode") not in VALID_TOUR_MODES:
        return _rejection(event, "invalid_phase", "导游模式无效，无法处理本次操作。", tour_state, interaction_state)
    if interaction_state.get("stop_phase") not in VALID_STOP_PHASES:
        return _rejection(event, "invalid_phase", "当前导游阶段无效，无法处理本次操作。", tour_state, interaction_state)
    finished = tour_state.get("route_status") == "completed" or interaction_state.get("stop_phase") == "finished"
    if finished and not allow_finished_idempotent:
        return _rejection(event, "tour_finished", "本次游览已经结束。", tour_state, interaction_state)
    return None


def _next_pending(tour_state: dict[str, Any]) -> str | None:
    return tour_state["remaining_stop_ids"][0] if tour_state["remaining_stop_ids"] else None


def _navigation_data(tour_state: dict[str, Any], target_stop_id: str | None = None) -> dict[str, Any]:
    if target_stop_id is None:
        return {"navigation": None}
    navigation = next_stop_navigation(tour_state, target_stop_id=target_stop_id)
    return {"navigation": navigation}


def handle_tour_event(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    event: str,
    **payload: Any,
) -> dict[str, Any]:
    """Handle one contract-whitelisted event without mutating either input."""
    if event not in EVENTS:
        return _rejection(event, "invalid_event", "不支持该游览操作。", tour_state, interaction_state)
    if event == "finish_tour":
        return _finish(tour_state, interaction_state)
    context_error = _validate_context(event, tour_state, interaction_state)
    if context_error:
        return context_error
    assert tour_state is not None and interaction_state is not None
    handlers = {
        "arrive_at_stop": _arrive,
        "next_stop": _next,
        "skip_stop": _skip,
        "replan_time": _replan_time,
        "request_stop_detail": _request_detail,
        "confirm_stop_complete": _confirm_complete,
    }
    return handlers[event](tour_state, interaction_state, **payload)


def _arrive(
    tour_state: dict[str, Any], interaction_state: dict[str, Any], *, node_id: str | None = None, **_: Any
) -> dict[str, Any]:
    if not node_id or node_id not in known_node_ids():
        return _rejection("arrive_at_stop", "invalid_node_id", "该点位不在已审核空间节点表中。", tour_state, interaction_state)
    pending = interaction_state.get("pending_stop_id")
    phase = interaction_state.get("stop_phase")
    if node_id == pending:
        if tour_state.get("current_stop_id") == node_id and phase in {"explaining", "awaiting_confirmation"}:
            return _result(
                ok=True, event="arrive_at_stop", code="arrived", message="已处于该讲解点，等待您确认讲解完成。",
                tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
            )
        updated_tour = _record_arrival(tour_state, node_id, "planned_stop")
        updated_interaction = {**interaction_state, "pending_stop_id": node_id, "stop_phase": "explaining"}
        return _result(
            ok=True, event="arrive_at_stop", code="arrived", message="已到达当前正式讲解点，可开始讲解。",
            tour_state=updated_tour, interaction_state=updated_interaction,
        )

    # Frozen contract: a legal non-pending location is a self-arrival.  It
    # records reality but never alters the formal route order or visit counts.
    if tour_state.get("current_stop_id") == node_id and tour_state.get("last_arrival_kind") == "self_arrival":
        return _result(
            ok=True, event="arrive_at_stop", code="self_arrival", message="当前位置已记录，正式路线保持不变。",
            tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
        )
    updated_tour = _record_arrival(tour_state, node_id, "self_arrival")
    updated_interaction = {**interaction_state, "stop_phase": "navigating"}
    return _result(
        ok=True, event="arrive_at_stop", code="self_arrival", message="已记录您的当前位置；正式下一站与原路线顺序保持不变。",
        tour_state=updated_tour, interaction_state=updated_interaction,
        data=_navigation_data(updated_tour, pending),
    )


def _next(tour_state: dict[str, Any], interaction_state: dict[str, Any], **_: Any) -> dict[str, Any]:
    if interaction_state["stop_phase"] in {"explaining", "awaiting_confirmation"}:
        return _rejection("next_stop", "invalid_phase", "请先确认当前点讲解完成，或选择跳过当前点。", tour_state, interaction_state)
    pending = interaction_state.get("pending_stop_id")
    if pending is None:
        return _rejection("next_stop", "no_remaining_stop", "当前没有待前往的正式讲解点。", tour_state, interaction_state)
    return _result(
        ok=True, event="next_stop", code="next_stop_ready", message="已生成前往下一正式讲解点的指引。",
        tour_state=tour_state, interaction_state=interaction_state, data=_navigation_data(tour_state, pending),
    )


def _skip(
    tour_state: dict[str, Any], interaction_state: dict[str, Any], *, node_id: str | None = None, **_: Any
) -> dict[str, Any]:
    current = tour_state.get("current_stop_id")
    target = node_id or (current if current in tour_state["remaining_stop_ids"] else interaction_state.get("pending_stop_id"))
    if target is None:
        return _rejection("skip_stop", "no_remaining_stop", "当前没有可跳过的正式讲解点。", tour_state, interaction_state)
    if target in tour_state.get("skipped_stop_ids", []):
        return _result(
            ok=True, event="skip_stop", code="already_skipped", message="该讲解点此前已跳过。",
            tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
        )
    if target not in tour_state["remaining_stop_ids"]:
        return _rejection("skip_stop", "stop_not_in_route", "只能跳过当前路线中尚未完成的正式讲解点。", tour_state, interaction_state)
    try:
        replanned = replan_after_skip(tour_state, target)
    except (TourStateError, ValueError) as exc:
        return _rejection("skip_stop", "stop_not_in_route", f"无法跳过该点：{exc}", tour_state, interaction_state)
    updated_tour = replanned.tour_state
    pending = _next_pending(updated_tour)
    updated_interaction = {
        **interaction_state,
        "pending_stop_id": pending,
        "stop_phase": "finished" if pending is None else "navigating",
    }
    return _result(
        ok=True, event="skip_stop", code="skipped", message="已跳过该正式讲解点，并更新剩余路线。",
        tour_state=updated_tour, interaction_state=updated_interaction,
        data={"plan": replanned.plan, **_navigation_data(updated_tour, pending)},
    )


def _replan_time(
    tour_state: dict[str, Any], interaction_state: dict[str, Any], *, available_minutes: int | None = None, **_: Any
) -> dict[str, Any]:
    if not isinstance(available_minutes, int) or available_minutes <= 0:
        return _rejection("replan_time", "invalid_minutes", "剩余时间必须是大于 0 的整数分钟。", tour_state, interaction_state)
    try:
        replanned = replan_remaining_time(tour_state, available_minutes)
    except (TourStateError, ValueError) as exc:
        return _rejection("replan_time", "invalid_minutes", f"无法按该剩余时间重规划：{exc}", tour_state, interaction_state)
    updated_tour = replanned.tour_state
    active_current = (
        tour_state.get("current_stop_id")
        and tour_state.get("current_stop_id") == interaction_state.get("pending_stop_id")
        and tour_state.get("current_stop_id") in updated_tour["remaining_stop_ids"]
        and interaction_state.get("stop_phase") in {"explaining", "awaiting_confirmation"}
    )
    pending = tour_state["current_stop_id"] if active_current else _next_pending(updated_tour)
    phase = interaction_state["stop_phase"] if active_current else ("finished" if pending is None else "navigating")
    updated_interaction = {**interaction_state, "pending_stop_id": pending, "stop_phase": phase}
    return _result(
        ok=True, event="replan_time", code="replanned", message="已按新的剩余时间更新路线。",
        tour_state=updated_tour, interaction_state=updated_interaction,
        data={"plan": replanned.plan, **_navigation_data(updated_tour, pending if phase == "navigating" else None)},
    )


def _finish(tour_state: dict[str, Any] | None, interaction_state: dict[str, Any] | None) -> dict[str, Any]:
    if tour_state is None or interaction_state is None:
        return _rejection("finish_tour", "route_not_initialized", "请先建立游览路线。", tour_state, interaction_state)
    if tour_state.get("route_status") == "completed" or interaction_state.get("stop_phase") == "finished":
        return _result(
            ok=True, event="finish_tour", code="tour_already_finished", message="本次游览此前已结束。",
            tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
        )
    updated_tour = _finish_tour(tour_state)
    updated_interaction = {**interaction_state, "pending_stop_id": None, "stop_phase": "finished"}
    return _result(
        ok=True, event="finish_tour", code="tour_finished", message="已结束本次游览，并保留真实游览记录。",
        tour_state=updated_tour, interaction_state=updated_interaction,
    )


def _request_detail(tour_state: dict[str, Any], interaction_state: dict[str, Any], **_: Any) -> dict[str, Any]:
    if interaction_state["stop_phase"] not in {"explaining", "awaiting_confirmation"}:
        return _rejection("request_stop_detail", "invalid_phase", "请先到达当前正式讲解点后再展开讲解。", tour_state, interaction_state)
    return _result(
        ok=True, event="request_stop_detail", code="detail_placeholder",
        message="该点的可展开讲解将在后续 A2 RAG 编排阶段接入；当前不改变游览记录。",
        tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
    )


def _confirm_complete(tour_state: dict[str, Any], interaction_state: dict[str, Any], **_: Any) -> dict[str, Any]:
    current = tour_state.get("current_stop_id")
    pending = interaction_state.get("pending_stop_id")
    if current in tour_state.get("visited_stop_ids", []) and interaction_state["stop_phase"] == "navigating":
        return _result(
            ok=True, event="confirm_stop_complete", code="already_completed", message="该讲解点此前已确认完成。",
            tour_state=tour_state, interaction_state=interaction_state, idempotent=True,
        )
    if current != pending or current not in tour_state["remaining_stop_ids"]:
        return _rejection("confirm_stop_complete", "not_current_stop", "只能确认当前已到达且尚未完成的正式讲解点。", tour_state, interaction_state)
    if interaction_state["stop_phase"] not in {"explaining", "awaiting_confirmation"}:
        return _rejection("confirm_stop_complete", "invalid_phase", "当前尚未进入可确认完成的讲解阶段。", tour_state, interaction_state)
    try:
        updated_tour = _complete_current_stop(tour_state, current)
    except TourStateError as exc:
        return _rejection("confirm_stop_complete", "not_current_stop", f"无法确认该讲解点：{exc}", tour_state, interaction_state)
    pending = _next_pending(updated_tour)
    updated_interaction = {
        **interaction_state,
        "pending_stop_id": pending,
        "stop_phase": "finished" if pending is None else "navigating",
    }
    return _result(
        ok=True, event="confirm_stop_complete", code="stop_completed", message="已确认完成当前讲解点。",
        tour_state=updated_tour, interaction_state=updated_interaction,
        data=_navigation_data(updated_tour, pending),
    )
