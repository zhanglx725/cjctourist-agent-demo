"""Deterministic next-stop navigation derived from TourState and reviewed edges."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spatial_graph import build_spatial_graph, shortest_route
from tour_state import ENTRY_NODE_ID, TourStateError, next_stop


CATALOG_FILE = Path("data/chen_clan_academy/routes/route_stop_catalog_v1.csv")


class TourNavigationError(ValueError):
    """Raised when a next-stop instruction cannot use reviewed route data."""


@dataclass(frozen=True)
class NextStopNavigation:
    from_node_id: str
    next_stop_id: str
    next_stop_name: str
    guide_focus: str
    path_node_ids: tuple[str, ...]
    path_names: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_walk_seconds: int | None
    walk_time_basis: tuple[str, ...]
    warning: str


def _load_catalog(path: Path = CATALOG_FILE) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["node_id"]: row for row in csv.DictReader(handle)}


def resolve_route_stop_from_text(user_text: str) -> str | None:
    """Resolve an unambiguous formal guide-stop name mentioned by a visitor."""
    matches = [
        (row["stop_name"], node_id)
        for node_id, row in _load_catalog().items()
        if row["stop_name"] and row["stop_name"] in user_text
    ]
    if not matches:
        return None
    # Longest name wins, so “前院中部” is not shadowed by any shorter alias.
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def next_stop_navigation(
    state: dict[str, Any], target_stop_id: str | None = None
) -> NextStopNavigation | None:
    """Return reviewed walking guidance to the next formal remaining stop.

    ``None`` means there are no remaining guide stops.  It is not an error,
    because completed tours should naturally have no next destination.
    """
    try:
        target_id = target_stop_id if target_stop_id is not None else next_stop(state)
    except TourStateError as exc:
        raise TourNavigationError(f"TourState 无法导航：{exc}") from exc
    if target_id is None:
        return None
    if target_id not in state["remaining_stop_ids"]:
        raise TourNavigationError("下一讲解点必须是当前路线中尚未完成的正式讲解点。")
    source_id = state["current_stop_id"] or ENTRY_NODE_ID
    graph = build_spatial_graph()
    if source_id not in graph:
        raise TourNavigationError(f"当前点位不在已审核空间图中：{source_id}")
    catalog = _load_catalog()
    card = catalog.get(target_id)
    if card is None:
        raise TourNavigationError(f"下一讲解点缺少点位讲解目录：{target_id}")
    spatial = shortest_route(source_id, target_id, graph)
    return NextStopNavigation(
        from_node_id=source_id,
        next_stop_id=target_id,
        next_stop_name=card["stop_name"],
        guide_focus=card["guide_focus"],
        path_node_ids=spatial.node_ids,
        path_names=spatial.names,
        edge_ids=spatial.edge_ids,
        estimated_walk_seconds=spatial.estimated_walk_seconds,
        walk_time_basis=spatial.walk_time_basis,
        warning="预计步行时间基于官网地图和已核对路线估算，现场请以馆方指引为准。",
    )


def format_next_stop_navigation(instruction: NextStopNavigation | None) -> str:
    """Render a compact deterministic visitor-facing navigation message."""
    if instruction is None:
        return "当前路线的正式讲解点均已完成或跳过。您可以结束游览，或告诉我是否需要重新规划。"
    walk = (
        f"约 {instruction.estimated_walk_seconds} 秒"
        if instruction.estimated_walk_seconds is not None
        else "时间待现场复核"
    )
    middle = " → ".join(instruction.path_names)
    return (
        f"下一站：{instruction.next_stop_name}\n"
        f"从当前位置经 {middle} 前往，预计步行 {walk}。\n"
        f"到达后重点看：{instruction.guide_focus}\n"
        f"提示：{instruction.warning}"
    )
