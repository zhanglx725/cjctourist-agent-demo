"""Deterministic planning over reviewed Chen Clan Academy route data.

Reviewed templates expand into safe walking segments here. E4-3B compares those
anchors with dynamic reviewed candidates through ``route_selection``; neither
path may exceed the visitor's requested time budget.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from spatial_graph import SpatialGraphError, build_spatial_graph, shortest_route


ROUTES_DIR = Path("data/chen_clan_academy/routes")
CATALOG_FILE = ROUTES_DIR / "route_stop_catalog_v1.csv"
TEMPLATES_FILE = ROUTES_DIR / "route_templates_v1.json"
POLICY_FILE = ROUTES_DIR / "route_policy_v1.json"


class RoutePlanningError(ValueError):
    """Raised when approved route data cannot produce a safe route plan."""


@dataclass(frozen=True)
class RouteSegment:
    from_stop_id: str
    to_stop_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_walk_seconds: int | None
    walk_time_basis: tuple[str, ...]


@dataclass(frozen=True)
class RoutePlan:
    route_id: str
    display_name: str
    target_minutes: int
    exit_node_id: str
    stop_ids: tuple[str, ...]
    full_path_node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    segments: tuple[RouteSegment, ...]
    estimated_walk_seconds: int | None
    estimated_exit_return_seconds: int | None
    estimated_explanation_seconds: int
    estimated_observation_seconds: int
    estimated_interaction_seconds: int
    estimated_buffer_seconds: int
    estimated_total_seconds: int | None
    within_time_budget: bool | None
    walk_time_basis: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = [asdict(segment) for segment in self.segments]
        return data


@dataclass(frozen=True)
class RemainingRoutePlan:
    """A shortened route from the visitor's actual current position."""

    route_id: str
    start_node_id: str
    exit_node_id: str
    stop_ids: tuple[str, ...]
    dropped_stop_ids: tuple[str, ...]
    full_path_node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_walk_seconds: int | None
    estimated_explanation_seconds: int
    estimated_observation_seconds: int
    estimated_interaction_seconds: int
    estimated_buffer_seconds: int
    estimated_total_seconds: int | None
    allowed_total_seconds: int
    within_time_budget: bool | None
    warning: str


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RoutePlanningError(f"路线数据文件不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_catalog(path: Path = CATALOG_FILE) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise RoutePlanningError(f"路线停靠点目录不存在：{path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["node_id"]: row for row in csv.DictReader(handle)}


def _template_by_id(route_id: str, templates: dict[str, Any]) -> dict[str, Any]:
    for template in templates.get("templates", []):
        if template.get("route_id") == route_id:
            return template
    raise RoutePlanningError(f"未知路线模板：{route_id}")


def _approved_stop_ids(template: dict[str, Any], catalog: dict[str, dict[str, str]]) -> None:
    for node_id in [*template["required_stop_ids"], *template.get("optional_stop_ids", [])]:
        row = catalog.get(node_id)
        if row is None:
            raise RoutePlanningError(f"路线模板引用了未登记停靠点：{node_id}")
        if row["review_status"] != "approved" or row["route_eligible"] != "true":
            raise RoutePlanningError(f"路线模板引用了未启用停靠点：{node_id}")


def _validate_stop_groups(template: dict[str, Any], policy: dict[str, Any]) -> None:
    selected = set(template["required_stop_ids"])
    group_policy = policy.get("stop_group_policy", {})
    maximum = int(group_policy.get("maximum_selected_per_group", 1))
    for group_name, members in group_policy.get("groups", {}).items():
        overlaps = selected.intersection(members)
        if len(overlaps) > maximum:
            raise RoutePlanningError(
                f"路线 {template['route_id']} 在互斥组 {group_name} 中重复停留："
                f"{', '.join(sorted(overlaps))}"
            )


def _filtered_graph(policy: dict[str, Any]):
    graph = build_spatial_graph()
    allowed = set(policy["path_policy"]["allowed_edge_statuses"])
    forbidden = [
        (start, end)
        for start, end, data in graph.edges(data=True)
        if data.get("status") not in allowed
    ]
    graph.remove_edges_from(forbidden)
    return graph


def plan_template(route_id: str) -> RoutePlan:
    """Expand one reviewed route template into shortest reviewed graph segments."""
    templates = _read_json(TEMPLATES_FILE)
    policy = _read_json(POLICY_FILE)
    catalog = _read_catalog()
    template = _template_by_id(route_id, templates)
    _approved_stop_ids(template, catalog)
    _validate_stop_groups(template, policy)

    graph = _filtered_graph(policy)
    stop_ids = tuple(template["stop_order"])
    exit_node_id = policy.get("exit_policy", {}).get("default_exit_node_id")
    if not exit_node_id or exit_node_id not in graph:
        raise RoutePlanningError("路线出口区域未配置或不在已审核空间图中。")
    if len(stop_ids) < 2:
        raise RoutePlanningError(f"路线 {route_id} 至少需要起点和一个讲解停留站")

    segments: list[RouteSegment] = []
    full_path: list[str] = []
    edge_ids: list[str] = []
    bases: list[str] = []
    for start, end in zip(stop_ids, stop_ids[1:]):
        try:
            spatial = shortest_route(start, end, graph=graph)
        except SpatialGraphError as exc:
            raise RoutePlanningError(f"路线 {route_id} 不可达：{exc}") from exc
        segments.append(
            RouteSegment(
                from_stop_id=start,
                to_stop_id=end,
                node_ids=spatial.node_ids,
                edge_ids=spatial.edge_ids,
                estimated_walk_seconds=spatial.estimated_walk_seconds,
                walk_time_basis=spatial.walk_time_basis,
            )
        )
        full_path.extend(spatial.node_ids if not full_path else spatial.node_ids[1:])
        edge_ids.extend(spatial.edge_ids)
        bases.extend(spatial.walk_time_basis)

    # Return to the front-courtyard exit area after the final guide stop.  This
    # is transit only: it never turns the exit node into a repeated explanation.
    exit_return_seconds: int | None = 0
    if stop_ids[-1] != exit_node_id:
        try:
            exit_spatial = shortest_route(stop_ids[-1], exit_node_id, graph=graph)
        except SpatialGraphError as exc:
            raise RoutePlanningError(f"路线 {route_id} 无法回到前院出口区：{exc}") from exc
        segments.append(
            RouteSegment(
                from_stop_id=stop_ids[-1],
                to_stop_id=exit_node_id,
                node_ids=exit_spatial.node_ids,
                edge_ids=exit_spatial.edge_ids,
                estimated_walk_seconds=exit_spatial.estimated_walk_seconds,
                walk_time_basis=exit_spatial.walk_time_basis,
            )
        )
        full_path.extend(exit_spatial.node_ids[1:])
        edge_ids.extend(exit_spatial.edge_ids)
        bases.extend(exit_spatial.walk_time_basis)
        exit_return_seconds = exit_spatial.estimated_walk_seconds

    guide_stop_ids = tuple(
        node_id
        for node_id in stop_ids
        if node_id in catalog and catalog[node_id]["route_eligible"] == "true"
    )
    if len(guide_stop_ids) != len(set(guide_stop_ids)) and not policy["path_policy"].get(
        "allow_repeated_guide_stops", False
    ):
        raise RoutePlanningError(f"路线 {route_id} 重复安排了同一讲解停留站")

    explanation_seconds = sum(
        int(catalog[node_id]["recommended_visit_minutes"]) * 60
        for node_id in guide_stop_ids
    )
    experience = template.get("experience_budget", {})
    observation_seconds = len(guide_stop_ids) * int(
        experience.get("observation_seconds_per_stop", 0)
    )
    interaction_seconds = len(guide_stop_ids) * int(
        experience.get("interaction_seconds_per_stop", 0)
    )
    # The entry context has no long-form guide slot, but still receives a small
    # arrival/transition buffer like every listed stop.
    buffer_seconds = len(stop_ids) * int(policy["time_policy"]["per_stop_buffer_seconds"])
    walk_times = [segment.estimated_walk_seconds for segment in segments]
    total_walk = sum(walk_times) if all(value is not None for value in walk_times) else None
    total_seconds = (
        total_walk
        + explanation_seconds
        + observation_seconds
        + interaction_seconds
        + buffer_seconds
        if total_walk is not None
        else None
    )
    budget_seconds = int(template["target_minutes"]) * 60
    within_budget = total_seconds <= budget_seconds if total_seconds is not None else None
    warnings = [templates["rules"]["time_warning"], policy["time_policy"]["time_warning"]]
    warnings.append("完整路径已包含回到前院出口区的步行时间；出口开放情况仍需以现场为准。")
    if not within_budget:
        warnings.append("当前模板预计超过目标时长；后续需由规划器删减可选站或调整讲解时长。")

    return RoutePlan(
        route_id=route_id,
        display_name=template["display_name"],
        target_minutes=int(template["target_minutes"]),
        exit_node_id=exit_node_id,
        stop_ids=stop_ids,
        full_path_node_ids=tuple(full_path),
        edge_ids=tuple(edge_ids),
        segments=tuple(segments),
        estimated_walk_seconds=total_walk,
        estimated_exit_return_seconds=exit_return_seconds,
        estimated_explanation_seconds=explanation_seconds,
        estimated_observation_seconds=observation_seconds,
        estimated_interaction_seconds=interaction_seconds,
        estimated_buffer_seconds=buffer_seconds,
        estimated_total_seconds=total_seconds,
        within_time_budget=within_budget,
        walk_time_basis=tuple(dict.fromkeys(bases)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def recommend_route(
    available_minutes: int | None = None,
    interests: list[str] | None = None,
    detail_level: str = "standard",
):
    """Return the v2 multi-objective reviewed-route selection result.

    The previous title-theme-first, 10%-overrun anchor ranking was retired in
    E4-3B.  Import lazily to keep ``route_selection`` free to read this module's
    reviewed-template expansion functions without an import cycle.
    """
    from route_selection import recommend_route as recommend_mult_objective_route

    return recommend_mult_objective_route(
        available_minutes=available_minutes or 30,
        interests=interests,
        detail_level=detail_level,
    )


def _remaining_route_estimate(
    graph: Any,
    start_node_id: str,
    stop_ids: list[str],
    exit_node_id: str,
    catalog: dict[str, dict[str, str]],
    observation_each: int,
    interaction_each: int,
    buffer_each: int,
) -> tuple[tuple[str, ...], tuple[str, ...], int | None, int, int, int, int, int | None]:
    """Build a path and complete time budget for a fixed ordered stop list."""
    current = start_node_id
    full_path = [current]
    edge_ids: list[str] = []
    walk_values: list[int | None] = []
    for target in [*stop_ids, exit_node_id]:
        if target == current:
            continue
        spatial = shortest_route(current, target, graph=graph)
        full_path.extend(spatial.node_ids[1:])
        edge_ids.extend(spatial.edge_ids)
        walk_values.append(spatial.estimated_walk_seconds)
        current = target
    walk = sum(walk_values) if all(value is not None for value in walk_values) else None
    explanation = sum(int(catalog[node_id]["recommended_visit_minutes"]) * 60 for node_id in stop_ids)
    observation = len(stop_ids) * observation_each
    interaction = len(stop_ids) * interaction_each
    buffer = len(stop_ids) * buffer_each
    total = walk + explanation + observation + interaction + buffer if walk is not None else None
    return tuple(full_path), tuple(edge_ids), walk, explanation, observation, interaction, buffer, total


def plan_from_current_position(
    current_stop_id: str | None,
    remaining_minutes: int,
    excluded_stop_ids: list[str] | None,
    preferred_route_id: str,
    candidate_stop_ids: list[str] | None = None,
) -> RemainingRoutePlan:
    """Shorten a reviewed route from the current position without inventing stops.

    ``candidate_stop_ids`` is used by TourState to preserve its real unfinished
    route order (including a prior dynamic route).  When omitted, the planner
    takes the remaining suffix of the preferred reviewed template.
    """
    if remaining_minutes <= 0:
        raise RoutePlanningError("剩余时间必须大于 0。")
    templates = _read_json(TEMPLATES_FILE)
    policy = _read_json(POLICY_FILE)
    catalog = _read_catalog()
    graph = _filtered_graph(policy)
    start = current_stop_id or templates["rules"]["start_node_id"]
    if start not in graph:
        raise RoutePlanningError(f"当前起点不在已审核空间图中：{start}")
    exit_node_id = policy["exit_policy"]["default_exit_node_id"]
    excluded = set(excluded_stop_ids or [])
    template = next((item for item in templates["templates"] if item["route_id"] == preferred_route_id), None)
    if candidate_stop_ids is None:
        if template is None:
            raise RoutePlanningError("动态路线重规划必须提供 TourState 的剩余点顺序。")
        ordered = [node for node in template["stop_order"] if node != templates["rules"]["start_node_id"]]
        if start in ordered:
            ordered = ordered[ordered.index(start) + 1 :]
    else:
        ordered = list(candidate_stop_ids)
    ordered = [node for node in ordered if node not in excluded and node != start]
    unknown = set(ordered).difference(catalog)
    if unknown:
        raise RoutePlanningError(f"重规划点不在讲解点目录中：{', '.join(sorted(unknown))}")
    experience = template.get("experience_budget", {}) if template else {}
    observation_each = int(experience.get("observation_seconds_per_stop", 180))
    interaction_each = int(experience.get("interaction_seconds_per_stop", 120))
    buffer_each = int(policy["time_policy"]["per_stop_buffer_seconds"])
    allowed = int(remaining_minutes * 60)

    kept = list(ordered)
    dropped: list[str] = []
    priority_rank = {"low": 0, "medium": 1, "high": 2}
    while kept:
        *_, total = _remaining_route_estimate(
            graph, start, kept, exit_node_id, catalog, observation_each, interaction_each, buffer_each
        )
        if total is not None and total <= allowed:
            break
        # Remove optional points first.  Among equivalent roles/priority, drop
        # the later stop to retain the original route narrative as long as possible.
        removable = sorted(
            enumerate(kept),
            key=lambda item: (
                0 if catalog[item[1]]["route_role"] == "optional" else 1,
                priority_rank.get(catalog[item[1]]["priority"], 0),
                -item[0],
            ),
        )[0][0]
        dropped.append(kept.pop(removable))
    path, edges, walk, explanation, observation, interaction, buffer, total = _remaining_route_estimate(
        graph, start, kept, exit_node_id, catalog, observation_each, interaction_each, buffer_each
    )
    return RemainingRoutePlan(
        route_id=f"{preferred_route_id}_replanned",
        start_node_id=start,
        exit_node_id=exit_node_id,
        stop_ids=tuple(kept),
        dropped_stop_ids=tuple(dropped),
        full_path_node_ids=path,
        edge_ids=edges,
        estimated_walk_seconds=walk,
        estimated_explanation_seconds=explanation,
        estimated_observation_seconds=observation,
        estimated_interaction_seconds=interaction,
        estimated_buffer_seconds=buffer,
        estimated_total_seconds=total,
        allowed_total_seconds=allowed,
        within_time_budget=total <= allowed if total is not None else None,
        warning="剩余路线保留原顺序并包含回前院出口区的步行时间；时间为地图估算，待现场复核。",
    )
