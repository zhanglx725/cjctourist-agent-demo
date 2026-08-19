"""Deterministic, evidence-backed P4-01 tour opening program."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EVIDENCE_FILE = (
    Path(__file__).resolve().parent
    / "data"
    / "chen_clan_academy"
    / "tour_opening_evidence_v1.json"
)
VALID_STATUSES = {"pending", "played", "skipped"}


class TourOpeningProgramError(ValueError):
    pass


@dataclass(frozen=True)
class RouteOpeningBrief:
    """Scene-only input for a whole-route opening, never a stop body."""

    schema_version: str
    style_id: str
    first_stop_display_name: str


def build_route_opening_brief(
    *, style_id: str = "neutral", first_stop_display_name: str,
) -> RouteOpeningBrief:
    """Build the dedicated route-opening input without exposing point phrases."""
    first_stop = " ".join(str(first_stop_display_name or "").split())
    if not first_stop:
        raise TourOpeningProgramError("路线开场缺少第一站名称。")
    return RouteOpeningBrief(
        schema_version="route_opening_brief_v1",
        style_id=str(style_id or "neutral"),
        first_stop_display_name=first_stop,
    )


def render_route_opening(
    facts: list[str], brief: RouteOpeningBrief,
) -> str:
    """Render a route-level opening from route evidence and a route brief only."""
    if not facts or not all(str(fact).strip() for fact in facts):
        raise TourOpeningProgramError("开场资料为空。")
    return (
        "欢迎来到陈家祠。本次将沿已确认路线，从整体空间与建筑装饰工艺入门，"
        f"第一站先到{brief.first_stop_display_name}。"
        + "".join(str(fact).strip() for fact in facts)
        + "接下来请按已确认路线继续游览。"
    )


def initialize_tour_opening() -> dict[str, Any]:
    return {
        "status": "pending",
        "play_count": 0,
        "evidence_version": "tour_opening_evidence_v1",
        "last_action": "route_initialized",
    }


def opening_action(text: str) -> str | None:
    compact = "".join(str(text).strip().split()).rstrip("。！!？?")
    if compact in {
        "跳过开场", "跳过介绍", "跳过总体介绍", "不用介绍",
        "直接开始游览", "直接开始导游",
    }:
        return "skip"
    if compact in {"重播开场", "重播介绍", "再讲一次开场", "再介绍一次陈家祠"}:
        return "replay"
    if compact in {"播放开场", "开始介绍", "开始导游", "介绍一下陈家祠"}:
        return "play"
    return None


def is_tour_start_entry(text: str) -> bool:
    """Recognize route-less tour entry controls without claiming site QA."""
    compact = "".join(str(text).strip().split()).rstrip("。！!？?")
    return compact in {
        "开始导游", "开始导览", "开始游览", "带我参观", "带我游览",
    }


def _load_approved_evidence() -> dict[str, Any]:
    try:
        payload = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TourOpeningProgramError("开场资料不可用。") from exc
    if payload.get("review_status") != "approved":
        raise TourOpeningProgramError("开场资料当前不可用。")
    facts = payload.get("facts")
    if not isinstance(facts, list) or not facts:
        raise TourOpeningProgramError("开场资料为空。")
    for fact in facts:
        if not isinstance(fact, dict) or not str(fact.get("public_text") or "").strip():
            raise TourOpeningProgramError("开场资料格式无效。")
        if not fact.get("source_ids"):
            raise TourOpeningProgramError("开场事实缺少来源。")
    return payload


def apply_tour_opening_action(
    program: dict[str, Any] | None, action: str,
    *, route_opening_brief: RouteOpeningBrief | None = None,
) -> dict[str, Any]:
    current = deepcopy(program) if isinstance(program, dict) else initialize_tour_opening()
    if current.get("status") not in VALID_STATUSES:
        raise TourOpeningProgramError("开场程序状态无效。")
    if action == "skip":
        current.update({"status": "skipped", "last_action": "skipped"})
        return {
            "program": current,
            "message": "已跳过总体介绍。可以按路线前往第一站；需要时可说“重播开场”。",
            "audit": {"action": "skip", "state_writes": ["tour_opening_program"]},
        }
    if action not in {"play", "replay"}:
        raise TourOpeningProgramError("不支持的开场操作。")
    if action == "play" and current.get("status") != "pending":
        return {
            "program": current,
            "message": "本次路线的总体介绍已经处理过；如需再听，请说“重播开场”。",
            "audit": {"action": "play", "idempotent": True, "state_writes": []},
        }
    evidence = _load_approved_evidence()
    facts = [str(item["public_text"]).strip() for item in evidence["facts"]]
    current.update({
        "status": "played",
        "play_count": int(current.get("play_count") or 0) + 1,
        "last_action": action,
        "evidence_version": str(evidence["version"]),
    })
    # Older callers receive the historic deterministic shell.  Public graph
    # callers must provide the route-only brief, which is intentionally
    # separate from point narration components.
    message = (
        render_route_opening(facts, route_opening_brief)
        if route_opening_brief is not None
        else "欢迎来到陈家祠。" + "".join(facts) + "接下来请按已确认路线前往第一站。"
    )
    return {
        "program": current,
        "message": message,
        "audit": {
            "action": action,
            "evidence_version": evidence["version"],
            "fact_ids": [item["fact_id"] for item in evidence["facts"]],
            "source_ids": sorted({source for item in evidence["facts"] for source in item["source_ids"]}),
            "state_writes": ["tour_opening_program"],
        },
    }
