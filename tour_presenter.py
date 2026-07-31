"""Pure A1-3 presentation protocol for deterministic tour interaction results.

This module converts an adapter response into visitor-facing Chinese text and
stable action descriptors.  It never calls an LLM/RAG and never changes either
TourState or interaction state.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

from route_planner import CATALOG_FILE, _read_catalog
from tour_interaction import EVENTS
from tour_navigation import next_stop_navigation


MARKERS_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")


@lru_cache(maxsize=1)
def _marker_names() -> dict[str, str]:
    with MARKERS_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["node_id"]: row["name"]
            for row in csv.DictReader(handle)
            if row.get("node_id") and row.get("name")
        }


def _stop_name(node_id: str | None) -> str | None:
    if not node_id:
        return None
    return _read_catalog(CATALOG_FILE).get(node_id, {}).get(
        "stop_name", _marker_names().get(node_id, node_id)
    )


def _action(
    event_id: str,
    label: str,
    arguments: dict[str, Any] | None = None,
    *,
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_id not in EVENTS:
        raise ValueError(f"Action must use a frozen event ID: {event_id}")
    action = {
        "id": event_id,
        "label": label,
        "enabled": True,
        "arguments": dict(arguments or {}),
    }
    if input_schema:
        action["input_schema"] = input_schema
    return action


def _time_replan_action() -> dict[str, Any]:
    return _action(
        "replan_time",
        "调整剩余时间",
        input_schema={
            "available_minutes": {
                "type": "integer",
                "minimum": 1,
                "label": "还剩多少分钟？",
            }
        },
    )


def available_actions(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return only contract events that are meaningful in the current phase."""
    if not tour_state or not interaction_state:
        return []
    phase = interaction_state.get("stop_phase")
    pending = interaction_state.get("pending_stop_id")
    current = tour_state.get("current_stop_id")
    remaining = set(tour_state.get("remaining_stop_ids", []))
    if phase == "finished" or tour_state.get("route_status") == "completed":
        return []

    common = [_time_replan_action(), _action("finish_tour", "结束导览")]
    if phase == "navigating":
        if not pending:
            return common
        name = _stop_name(pending)
        return [
            _action("next_stop", "查看前往下一站的指引"),
            _action("arrive_at_stop", f"我已到达{name}", {"node_id": pending}),
            _action("skip_stop", f"跳过{name}", {"node_id": pending}),
            *common,
        ]

    if phase == "explaining":
        target = current if current in remaining else pending
        actions = [
            _action("explanation_finished", "本点讲解结束"),
            _action("request_stop_detail", "再讲详细一点"),
        ]
        if target:
            actions.append(_action("skip_stop", "跳过本点", {"node_id": target}))
        return [*actions, *common]

    if phase == "awaiting_confirmation":
        target = current if current in remaining else pending
        actions = [
            _action("confirm_stop_complete", "讲完了，去下一站"),
            _action("request_stop_detail", "再讲详细一点"),
        ]
        if target:
            actions.append(_action("skip_stop", "跳过本点", {"node_id": target}))
        return [*actions, *common]
    return []


def _message_for_result(result: dict[str, Any]) -> str:
    state = result.get("tour_state") or {}
    interaction = result.get("interaction_state") or {}
    code = result.get("code")
    current_name = _stop_name(state.get("current_stop_id"))
    pending_name = _stop_name(interaction.get("pending_stop_id"))
    if not result.get("ok"):
        return str(result.get("message") or "当前操作无法执行，请根据提示继续。")
    if code == "arrived":
        return f"你已到达{current_name or '当前讲解点'}，可以开始本点讲解。"
    if code == "self_arrival":
        suffix = f"正式下一站仍是{pending_name}。" if pending_name else "正式路线保持不变。"
        return f"已记录你当前位于{current_name or '该位置'}，{suffix}"
    if code in {"explanation_finished", "explanation_already_finished"}:
        return "本点讲解已结束。请确认是否完成参观，也可以继续了解或跳过本点。"
    if code in {"stop_completed", "already_completed"}:
        if interaction.get("stop_phase") == "finished":
            return "最后一站已确认完成，本次导览已结束。"
        return f"本点已完成。现在可前往下一站{pending_name or ''}。"
    if code in {"skipped", "already_skipped"}:
        return f"已更新路线。下一站是{pending_name or '后续讲解点'}。"
    if code == "replanned":
        return f"已按新的剩余时间调整路线。下一站是{pending_name or '后续讲解点'}。"
    if code == "replan_proposal_applied":
        return f"已应用新的后续路线。下一站是{pending_name or '后续讲解点'}。"
    if code == "next_stop_ready":
        return f"下一站是{pending_name or '后续讲解点'}，请按导航前往。"
    if code in {"tour_finished", "tour_already_finished"}:
        return "本次导览已结束，已保留真实的已完成与跳过记录。"
    return str(result.get("message") or "导览状态已更新。")


def present_tour_event(result: dict[str, Any]) -> dict[str, Any]:
    """Create a stable, UI-neutral presentation response from adapter output."""
    interaction = result.get("interaction_state") or {}
    return {
        "message": _message_for_result(result),
        "phase": interaction.get("stop_phase"),
        "actions": available_actions(result.get("tour_state"), interaction) if result.get("ok") else [],
        "navigation": (result.get("data") or {}).get("navigation"),
        "event": result.get("event"),
        "code": result.get("code"),
        "ok": bool(result.get("ok")),
        "idempotent": bool(result.get("idempotent")),
    }


def present_replan_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Present a non-mutating P1-11 route preview without exposing old pending."""
    origin_name = _stop_name(proposal.get("origin_node_id")) or "当前位置"
    stop_names = [_stop_name(node_id) or str(node_id) for node_id in proposal.get("stop_ids", [])]
    seconds = proposal.get("estimated_total_seconds")
    estimate = f"约 {round(int(seconds) / 60)} 分钟" if isinstance(seconds, int) else "时间待复核"
    return {
        "message": (
            f"已记录您当前位于{origin_name}。我已从{origin_name}出发，为您生成后续行程候选。\n"
            f"路线起点：{origin_name}\n"
            f"正式讲解停靠点：{'、'.join(stop_names)}\n"
            f"预计：{estimate}。\n\n"
            "该候选尚未替换原路线；请确认使用新路线，或取消并保留原路线。"
        ),
        "phase": "replan_route_confirmation",
        "actions": [
            _action("apply_replan_proposal", "确认使用新路线"),
            {"id": "cancel_replan_proposal", "label": "取消，保留原路线", "enabled": True, "arguments": {}},
        ],
        "navigation": None,
        "event": None,
        "code": "replan_route_confirmation",
        "ok": True,
        "idempotent": False,
    }


def present_replan_time_confirmation(confirmation: dict[str, Any]) -> dict[str, Any]:
    """Ask for an explicit live time budget before creating a route preview."""
    origin_name = _stop_name(confirmation.get("origin_node_id")) or "当前位置"
    return {
        "message": (
            f"已记录您当前位于{origin_name}，这与原路线的正式下一站不同。\n\n"
            "为了从这里重新安排后续行程，请告诉我您现在还剩多少时间，例如“我还有 30 分钟”。\n"
            "也可以回复“继续原路线”取消本次调整。"
        ),
        "phase": "replan_time_confirmation",
        "actions": [
            {
                "id": "provide_remaining_time",
                "label": "填写剩余时间",
                "enabled": True,
                "arguments": {},
                "input_schema": {"available_minutes": {"type": "integer", "minimum": 1, "label": "还剩多少分钟？"}},
            },
            {"id": "cancel_replan_proposal", "label": "继续原路线", "enabled": True, "arguments": {}},
        ],
        "navigation": None,
        "event": None,
        "code": "replan_time_confirmation",
        "ok": True,
        "idempotent": False,
    }


def present_tour_state(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    *,
    message: str | None = None,
) -> dict[str, Any]:
    """Present route initialization without changing either input snapshot."""
    pending_name = _stop_name((interaction_state or {}).get("pending_stop_id"))
    navigation = None
    if tour_state and (interaction_state or {}).get("pending_stop_id"):
        navigation = next_stop_navigation(tour_state)
    return {
        "message": message or f"路线已建立，下一站是{pending_name or '待确认讲解点'}。",
        "phase": (interaction_state or {}).get("stop_phase"),
        "actions": available_actions(tour_state, interaction_state),
        "navigation": navigation,
        "event": None,
        "code": "route_ready" if tour_state else "route_not_initialized",
        "ok": tour_state is not None and interaction_state is not None,
        "idempotent": False,
    }


def present_clarification(
    message: str,
    interaction_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a no-action clarification view without mutating tour state."""
    return {
        "message": message,
        "phase": (interaction_state or {}).get("stop_phase"),
        "actions": [],
        "navigation": None,
        "event": None,
        "code": "clarification",
        "ok": False,
        "idempotent": False,
    }
