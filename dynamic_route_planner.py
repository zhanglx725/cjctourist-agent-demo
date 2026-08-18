"""Path-aware dynamic route composition for Chen Clan Academy.

Only human-reviewed, ornament-rich stops are eligible.  The planner is
deterministic: it does not ask an LLM to invent passages or facts.  It uses
the reviewed spatial graph to balance cultural value, visitor interests,
walking detours and the available time budget.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from spatial_graph import build_spatial_graph, shortest_route


ROUTES_DIR = Path("data/chen_clan_academy/routes")
CATALOG_FILE = ROUTES_DIR / "route_stop_catalog_v1.csv"
POLICY_FILE = ROUTES_DIR / "dynamic_route_policy_v1.json"


@dataclass(frozen=True)
class DynamicRouteCandidate:
    node_id: str
    display_name: str
    route_role: str
    mapped_ornament_count: int
    mapped_craft_count: int
    recommended_visit_minutes: int
    themes: tuple[str, ...]
    representative_ornaments: tuple[str, ...]
    conflict_groups: tuple[str, ...]


@dataclass(frozen=True)
class CandidateScore:
    node_id: str
    total: float
    components: dict[str, float]


@dataclass(frozen=True)
class DynamicRoutePlan:
    requested_minutes: int
    detail_level: str
    start_node_id: str
    exit_node_id: str
    stop_ids: tuple[str, ...]
    full_path_node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    selected_scores: tuple[CandidateScore, ...]
    estimated_walk_seconds: int
    estimated_exit_return_seconds: int
    estimated_guide_seconds: int
    estimated_observation_seconds: int
    estimated_interaction_seconds: int
    estimated_total_seconds: int
    allowed_total_seconds: int
    time_basis_warning: str


class DynamicRouteCandidateError(ValueError):
    """Raised for invalid starts or malformed dynamic-route inputs."""


def load_dynamic_policy(path: Path = POLICY_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_stop_catalog(path: Path = CATALOG_FILE) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _canonical_group_members() -> dict[str, list[str]]:
    path = ROUTES_DIR / "route_policy_v1.json"
    route_policy = json.loads(path.read_text(encoding="utf-8"))
    return route_policy.get("stop_group_policy", {}).get("groups", {})


def eligible_dynamic_stops(
    catalog_rows: list[dict[str, str]] | None = None,
    policy: dict | None = None,
) -> list[DynamicRouteCandidate]:
    """Return stops meeting the reviewed dynamic-route eligibility rules."""
    policy = policy or load_dynamic_policy()
    catalog_rows = catalog_rows or load_stop_catalog()
    candidate_policy = policy["candidate_policy"]
    groups = _canonical_group_members()
    candidates: list[DynamicRouteCandidate] = []
    for row in catalog_rows:
        if row["review_status"] != candidate_policy["required_review_status"]:
            continue
        if row["route_role"] not in candidate_policy["allowed_route_roles"]:
            continue
        if row["route_eligible"] != "true":
            continue
        if int(row["mapped_ornament_count"]) < int(
            candidate_policy["minimum_mapped_ornament_count"]
        ):
            continue
        candidates.append(
            DynamicRouteCandidate(
                node_id=row["node_id"],
                display_name=row["stop_name"],
                route_role=row["route_role"],
                mapped_ornament_count=int(row["mapped_ornament_count"]),
                mapped_craft_count=int(row["mapped_craft_count"]),
                recommended_visit_minutes=int(row["recommended_visit_minutes"]),
                themes=tuple(filter(None, row["themes"].split(";"))),
                representative_ornaments=tuple(
                    filter(None, row["representative_ornaments"].split(";"))
                ),
                conflict_groups=tuple(
                    name for name, members in groups.items() if row["node_id"] in members
                ),
            )
        )
    return candidates


def filter_dynamic_candidates(
    start_node_id: str = "entrance_main_outside",
    excluded_stop_ids: list[str] | None = None,
) -> list[DynamicRouteCandidate]:
    """Filter eligible stops to those connected to the reviewed start node."""
    graph = build_spatial_graph()
    if start_node_id not in graph:
        raise DynamicRouteCandidateError(f"未知动态路线起点：{start_node_id}")
    excluded = set(excluded_stop_ids or [])
    import networkx as nx

    reachable = nx.node_connected_component(graph, start_node_id)
    return [
        candidate
        for candidate in eligible_dynamic_stops()
        if candidate.node_id in reachable and candidate.node_id not in excluded
    ]


def _interest_components(candidate: DynamicRouteCandidate, interests: list[str], weights: dict) -> dict[str, float]:
    """Score specific themes, representative items and generic craft intent."""
    themes = " ".join(candidate.themes)
    representatives = " ".join(candidate.representative_ornaments)
    generic_craft_terms = {"工艺", "装饰", "雕刻", "建筑装饰"}
    theme_match = 0.0
    representative_match = 0.0
    craft_intent = 0.0
    for term in interests:
        term = term.strip()
        if not term:
            continue
        if term in generic_craft_terms:
            craft_intent += candidate.mapped_craft_count * weights["craft_interest_per_type_bonus"]
        if term in themes:
            theme_match += weights["interest_match_bonus"]
        if term in representatives:
            representative_match += weights["representative_item_match_bonus"]
    return {
        "interest_theme_match": theme_match,
        "interest_representative_match": representative_match,
        "interest_craft_intent": craft_intent,
    }


def score_candidate(
    candidate: DynamicRouteCandidate,
    interests: list[str] | None = None,
    selected_candidates: list[DynamicRouteCandidate] | None = None,
    policy: dict | None = None,
) -> CandidateScore:
    """Return the explainable content score, before walking cost is applied."""
    policy = policy or load_dynamic_policy()
    weights = policy["scoring_policy"]
    interests = interests or []
    selected_candidates = selected_candidates or []
    selected_themes = {theme for item in selected_candidates for theme in item.themes}
    repeated_themes = len(selected_themes.intersection(candidate.themes))
    components = {
        "ornament_density": candidate.mapped_ornament_count * weights["mapped_ornament_weight"],
        "craft_diversity": candidate.mapped_craft_count * weights["mapped_craft_weight"],
        "route_role": weights[f"{candidate.route_role}_role_bonus"],
        **_interest_components(candidate, interests, weights),
        "theme_repeat_penalty": -repeated_themes * weights["same_theme_penalty"],
    }
    return CandidateScore(candidate.node_id, sum(components.values()), components)


def _maximum_stops(available_minutes: int, policy: dict) -> int:
    for threshold, value in policy["duration_policy"]["maximum_stops_by_duration"].items():
        if available_minutes <= int(threshold):
            return int(value)
    return int(list(policy["duration_policy"]["maximum_stops_by_duration"].values())[-1])


def _experience_per_stop(policy: dict, detail_level: str = "standard") -> tuple[int, int, int]:
    budgets = policy.get("experience_budget_per_stop_by_detail", {})
    budget = budgets.get(detail_level) or policy["experience_budget_per_stop_seconds"]
    return int(budget["guide"]), int(budget["observation"]), int(budget["interaction"])


def _has_conflict(candidate: DynamicRouteCandidate, selected: tuple[DynamicRouteCandidate, ...]) -> bool:
    candidate_groups = set(candidate.conflict_groups)
    return any(candidate_groups.intersection(item.conflict_groups) for item in selected)


def _compose_path(
    start_node_id: str,
    order: tuple[DynamicRouteCandidate, ...],
    graph,
    exit_node_id: str | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    nodes = [start_node_id]
    edges: list[str] = []
    walk_seconds = 0
    current = start_node_id
    for candidate in order:
        segment = shortest_route(current, candidate.node_id, graph)
        nodes.extend(segment.node_ids[1:])
        edges.extend(segment.edge_ids)
        walk_seconds += segment.estimated_walk_seconds or len(segment.edge_ids)
        current = candidate.node_id
    if exit_node_id and exit_node_id != current:
        segment = shortest_route(current, exit_node_id, graph)
        nodes.extend(segment.node_ids[1:])
        edges.extend(segment.edge_ids)
        walk_seconds += segment.estimated_walk_seconds or len(segment.edge_ids)
    return tuple(nodes), tuple(edges), walk_seconds


def _two_opt_order(
    start_node_id: str,
    order: tuple[DynamicRouteCandidate, ...],
    graph,
    exit_node_id: str,
) -> tuple[DynamicRouteCandidate, ...]:
    """Apply deterministic 2-opt reversals to remove needless walking detours."""
    best = order
    _, _, best_walk = _compose_path(start_node_id, best, graph, exit_node_id)
    improved = True
    while improved:
        improved = False
        for left, right in combinations(range(len(best)), 2):
            if right - left < 2:
                continue
            proposal = best[:left] + tuple(reversed(best[left:right])) + best[right:]
            _, _, proposal_walk = _compose_path(start_node_id, proposal, graph, exit_node_id)
            if proposal_walk < best_walk:
                best, best_walk, improved = proposal, proposal_walk, True
                break
        # Restart from the first pair after every accepted improvement.
    return best


def _order_utility(
    start_node_id: str,
    order: tuple[DynamicRouteCandidate, ...],
    interests: list[str],
    policy: dict,
    graph,
    exit_node_id: str,
) -> tuple[float, int]:
    """Evaluate a fixed visiting order using the same content/detour objective."""
    _, _, walk_seconds = _compose_path(start_node_id, order, graph, exit_node_id)
    content = sum(
        score_candidate(candidate, interests, list(order[:index]), policy).total
        for index, candidate in enumerate(order)
    )
    detour = walk_seconds * float(policy["scoring_policy"]["detour_penalty_per_second"])
    return content - detour, walk_seconds


def _local_replace_order(
    start_node_id: str,
    order: tuple[DynamicRouteCandidate, ...],
    candidates: list[DynamicRouteCandidate],
    interests: list[str],
    policy: dict,
    allowed_total: int,
    experience_each: int,
    graph,
    exit_node_id: str,
) -> tuple[DynamicRouteCandidate, ...]:
    """Try one-for-one substitutions when they improve route utility.

    This is deliberately bounded to a single pass: it is a transparent local
    improvement, not an opaque global optimiser.  It can trade a weak distant
    stop for a nearby interest-relevant stop while preserving all constraints.
    """
    best = order
    best_utility, best_walk = _order_utility(start_node_id, best, interests, policy, graph, exit_node_id)
    for index, current in enumerate(order):
        retained = best[:index] + best[index + 1 :]
        for replacement in candidates:
            if replacement == current or replacement in retained or _has_conflict(replacement, retained):
                continue
            proposal = retained[:index] + (replacement,) + retained[index:]
            utility, walk_seconds = _order_utility(start_node_id, proposal, interests, policy, graph, exit_node_id)
            if walk_seconds + len(proposal) * experience_each > allowed_total:
                continue
            if utility > best_utility:
                best, best_utility, best_walk = proposal, utility, walk_seconds
    return best


def _trim_order_to_time_cap(
    start_node_id: str,
    order: tuple[DynamicRouteCandidate, ...],
    interests: list[str],
    policy: dict,
    experience_each: int,
    graph,
    exit_node_id: str,
    maximum_seconds: int,
) -> tuple[DynamicRouteCandidate, ...]:
    """Remove the weakest stop until a detail-level upper band is met.

    Beam pruning can retain a rich near-cap route while discarding a shorter
    intermediate state. This deterministic repair only removes a reviewed stop;
    it never adds nodes, edges or unreviewed content.
    """
    trimmed = order
    minimum_stops = int(policy["route_quality_policy"].get("minimum_core_stops", 2))
    while len(trimmed) > minimum_stops:
        _, _, walk_seconds = _compose_path(start_node_id, trimmed, graph, exit_node_id)
        if walk_seconds + len(trimmed) * experience_each <= maximum_seconds:
            break
        ranked: list[tuple[float, int, str]] = []
        for index, candidate in enumerate(trimmed):
            content = score_candidate(candidate, interests, list(trimmed[:index]), policy).total
            # Optional stops are removed first when cultural utility is tied.
            role_penalty = 0 if candidate.route_role == "optional" else 1
            ranked.append((content, role_penalty, candidate.node_id))
        _, _, removed_id = sorted(ranked)[0]
        trimmed = tuple(candidate for candidate in trimmed if candidate.node_id != removed_id)
    return trimmed


def plan_dynamic_route(
    available_minutes: int,
    interests: list[str] | None = None,
    detail_level: str = "standard",
    start_node_id: str = "entrance_main_outside",
    excluded_stop_ids: list[str] | None = None,
    exit_node_id: str | None = None,
) -> DynamicRoutePlan:
    """Compose a reviewed dynamic route with path-aware selection and ordering.

    A bounded beam search evaluates each *next* stop from the visitor's current
    location.  Its utility is cultural score minus walking detour cost.  A
    final 2-opt pass removes local route reversals without changing selected
    stops.  This makes the result inspectable and stable for the same inputs.
    """
    policy = load_dynamic_policy()
    duration = policy["duration_policy"]
    if not int(duration["minimum_minutes"]) <= available_minutes <= int(duration["maximum_minutes"]):
        raise DynamicRouteCandidateError("请求时长超出动态路线支持范围。")
    if detail_level not in {"short", "standard", "deep"}:
        raise DynamicRouteCandidateError("讲解深度必须是 short、standard 或 deep。")
    interests = [term.strip() for term in (interests or []) if term.strip()]
    candidates = filter_dynamic_candidates(start_node_id, excluded_stop_ids)
    graph = build_spatial_graph()
    exit_node_id = exit_node_id or policy["exit_policy"]["default_exit_node_id"]
    if exit_node_id not in graph:
        raise DynamicRouteCandidateError(f"未知动态路线出口区域：{exit_node_id}")
    max_stops = _maximum_stops(available_minutes, policy)
    guide_each, observation_each, interaction_each = _experience_per_stop(policy, detail_level)
    experience_each = guide_each + observation_each + interaction_each
    allowed_total = int(available_minutes * 60)
    detour_penalty = float(policy["scoring_policy"]["detour_penalty_per_second"])
    time_fit_bonus = float(policy["scoring_policy"]["time_fit_bonus"])
    detail_bands = policy.get("selection_policy", {}).get("detail_time_bands", {})
    detail_lower, detail_upper = detail_bands.get(detail_level, (0.0, 1.0))

    # state = (utility, selected in visiting order, total seconds including experience)
    states: list[tuple[float, tuple[DynamicRouteCandidate, ...], int]] = [(0.0, (), 0)]
    beam_width = int(policy["route_quality_policy"].get("beam_width", 24))
    for _ in range(max_stops):
        expanded = list(states)  # Retain shorter valid routes as candidates.
        for utility, selected, total_seconds in states:
            current = selected[-1].node_id if selected else start_node_id
            for candidate in candidates:
                if candidate in selected or _has_conflict(candidate, selected):
                    continue
                segment = shortest_route(current, candidate.node_id, graph)
                segment_walk = segment.estimated_walk_seconds or len(segment.edge_ids)
                # Reserve the final return to the front-courtyard exit area at
                # every selection step, so a rich rear stop cannot consume the
                # whole budget and strand the visitor at the back of the site.
                exit_segment = shortest_route(candidate.node_id, exit_node_id, graph)
                exit_walk = exit_segment.estimated_walk_seconds or len(exit_segment.edge_ids)
                current_exit_walk = 0
                if selected:
                    current_exit = shortest_route(current, exit_node_id, graph)
                    current_exit_walk = current_exit.estimated_walk_seconds or len(current_exit.edge_ids)
                new_total = total_seconds + segment_walk + experience_each + exit_walk - current_exit_walk
                if new_total > allowed_total:
                    continue
                content = score_candidate(candidate, interests, list(selected), policy)
                remaining_ratio = max(0.0, 1 - (allowed_total - new_total) / allowed_total)
                next_utility = (
                    utility
                    + content.total
                    - segment_walk * detour_penalty
                    + remaining_ratio * time_fit_bonus
                )
                expanded.append((next_utility, selected + (candidate,), new_total))
        # Keep different orders, but bounded so planning remains fast and predictable.
        states = sorted(expanded, key=lambda item: (item[0], len(item[1])), reverse=True)[:beam_width]

    # First prefer states in the configured detail-level time-utilisation band.
    # This is a bounded candidate-pool choice, not an unbounded score multiplier:
    # cultural value and walking cost still rank plans inside the eligible pool.
    productive_states = [
        item for item in states
        if item[1] and detail_lower <= item[2] / allowed_total <= detail_upper
    ]
    final_states = productive_states or [item for item in states if item[1]]
    if not final_states:
        raise DynamicRouteCandidateError("在当前时长和排除条件下，没有可安排的讲解点。")
    # Prefer utility, then a route that makes productive use of its requested time.
    best_utility, selected, _ = max(
        final_states,
        key=lambda item: (item[0], len(item[1]), item[2]),
    )

    upper_band_seconds = int(allowed_total * float(detail_upper))
    selected = _trim_order_to_time_cap(
        start_node_id,
        selected,
        interests,
        policy,
        experience_each,
        graph,
        exit_node_id,
        upper_band_seconds,
    )
    selected = _local_replace_order(
        start_node_id,
        selected,
        candidates,
        interests,
        policy,
        allowed_total,
        experience_each,
        graph,
        exit_node_id,
    )
    selected = _trim_order_to_time_cap(
        start_node_id,
        selected,
        interests,
        policy,
        experience_each,
        graph,
        exit_node_id,
        upper_band_seconds,
    )
    ordered = _two_opt_order(start_node_id, selected, graph, exit_node_id)
    path_nodes, edge_ids, walk_seconds = _compose_path(start_node_id, ordered, graph, exit_node_id)
    selected_scores = tuple(
        score_candidate(candidate, interests, list(ordered[:index]), policy)
        for index, candidate in enumerate(ordered)
    )
    guide_seconds = len(ordered) * guide_each
    observation_seconds = len(ordered) * observation_each
    interaction_seconds = len(ordered) * interaction_each
    total_seconds = walk_seconds + guide_seconds + observation_seconds + interaction_seconds
    final_stop_id = ordered[-1].node_id
    exit_segment = shortest_route(final_stop_id, exit_node_id, graph)
    exit_return_seconds = exit_segment.estimated_walk_seconds or len(exit_segment.edge_ids)
    if total_seconds > allowed_total:
        # A 2-opt reversal cannot normally change feasibility, but retain the invariant.
        raise DynamicRouteCandidateError("路径优化后超出允许时间预算，请缩短时长或增加排除点。")
    return DynamicRoutePlan(
        requested_minutes=available_minutes,
        detail_level=detail_level,
        start_node_id=start_node_id,
        exit_node_id=exit_node_id,
        stop_ids=tuple(candidate.node_id for candidate in ordered),
        full_path_node_ids=path_nodes,
        edge_ids=edge_ids,
        selected_scores=selected_scores,
        estimated_walk_seconds=walk_seconds,
        estimated_exit_return_seconds=exit_return_seconds,
        estimated_guide_seconds=guide_seconds,
        estimated_observation_seconds=observation_seconds,
        estimated_interaction_seconds=interaction_seconds,
        estimated_total_seconds=total_seconds,
        allowed_total_seconds=allowed_total,
        time_basis_warning="步行时间（含回到前院出口区）基于官网地图与已审核边估算；讲解、观察和互动为动态预算，需现场复核。",
    )
