"""Deterministic route planning over the reviewed Chen Clan Academy space graph.

The planner selects no stops by itself in v1.  It expands a human-reviewed
template into reviewed walking segments, then reports the time budget and data
provenance.  Natural-language explanation belongs to the Agent layer later.
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
    stop_ids: tuple[str, ...]
    full_path_node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    segments: tuple[RouteSegment, ...]
    estimated_walk_seconds: int | None
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
    overrun_limit = 1 + float(policy["time_policy"]["maximum_overrun_ratio"])
    within_budget = total_seconds <= budget_seconds * overrun_limit if total_seconds is not None else None
    warnings = [templates["rules"]["time_warning"], policy["time_policy"]["time_warning"]]
    if not within_budget:
        warnings.append("当前模板预计超过目标时长；后续需由规划器删减可选站或调整讲解时长。")

    return RoutePlan(
        route_id=route_id,
        display_name=template["display_name"],
        target_minutes=int(template["target_minutes"]),
        stop_ids=stop_ids,
        full_path_node_ids=tuple(full_path),
        edge_ids=tuple(edge_ids),
        segments=tuple(segments),
        estimated_walk_seconds=total_walk,
        estimated_explanation_seconds=explanation_seconds,
        estimated_observation_seconds=observation_seconds,
        estimated_interaction_seconds=interaction_seconds,
        estimated_buffer_seconds=buffer_seconds,
        estimated_total_seconds=total_seconds,
        within_time_budget=within_budget,
        walk_time_basis=tuple(dict.fromkeys(bases)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def recommend_route(available_minutes: int | None = None, interests: list[str] | None = None) -> RoutePlan:
    """Choose a reviewed template by time fit, then by explicit theme overlap."""
    templates = _read_json(TEMPLATES_FILE)["templates"]
    plans = [(template, plan_template(template["route_id"])) for template in templates]
    if available_minutes is None:
        available_minutes = 30
    limit_seconds = available_minutes * 60 * 1.1
    feasible = [pair for pair in plans if pair[1].estimated_total_seconds <= limit_seconds]
    candidates = feasible or plans
    wanted = " ".join(interests or [])

    def rank(pair: tuple[dict[str, Any], RoutePlan]) -> tuple[int, int]:
        template, plan = pair
        overlap = sum(theme in wanted for theme in template.get("themes", []))
        difference = abs((plan.estimated_total_seconds or 0) - available_minutes * 60)
        return overlap, -difference

    return max(candidates, key=rank)[1]
