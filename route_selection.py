"""Deterministic multi-objective selection across reviewed route candidates.

This module never creates nodes, edges or cultural facts.  It compares reviewed
anchor templates with one reviewed dynamic composition under a strict time cap.
Interest evidence is derived only from the approved node-guide-card objects
already associated with the candidate's actual guide stops.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from typing import Any

from dynamic_route_planner import DynamicRoutePlan, plan_dynamic_route
from route_planner import RoutePlan, RoutePlanningError, TEMPLATES_FILE, plan_template


ROUTES_DIR = Path("data/chen_clan_academy/routes")
NODE_CARDS_FILE = ROUTES_DIR / "node_guide_cards_v1.json"
POLICY_FILE = ROUTES_DIR / "dynamic_route_policy_v1.json"
ENTRY_NODE_ID = "entrance_main_outside"


class RouteSelectionError(ValueError):
    """Raised only when no reviewed candidate can meet a strict route budget."""


@dataclass(frozen=True)
class RouteCandidateEvaluation:
    candidate_id: str
    route_strategy: str
    guide_stop_ids: tuple[str, ...]
    estimated_total_seconds: int
    requested_minutes: int
    detail_level: str
    interest_evidence: dict[str, tuple[dict[str, str], ...]]
    components: dict[str, float]
    total_score: float
    rejected_reason: str | None = None
    gap_from_best_score: float | None = None


@dataclass(frozen=True)
class RouteSelection:
    """A selected reviewed anchor or dynamic plan with auditable scoring."""

    plan: RoutePlan | DynamicRoutePlan
    route_id: str
    route_strategy: str
    requested_minutes: int
    detail_level: str
    guide_stop_ids: tuple[str, ...]
    selection_reason: dict[str, Any]

    @property
    def stop_ids(self) -> tuple[str, ...]:
        return self.plan.stop_ids

    @property
    def full_path_node_ids(self) -> tuple[str, ...]:
        return self.plan.full_path_node_ids

    @property
    def edge_ids(self) -> tuple[str, ...]:
        return self.plan.edge_ids

    @property
    def exit_node_id(self) -> str:
        return self.plan.exit_node_id

    @property
    def estimated_total_seconds(self) -> int:
        return int(self.plan.estimated_total_seconds or 0)

    @property
    def estimated_walk_seconds(self) -> int:
        return int(self.plan.estimated_walk_seconds or 0)

    @property
    def estimated_exit_return_seconds(self) -> int:
        return int(self.plan.estimated_exit_return_seconds or 0)

    @property
    def estimated_explanation_seconds(self) -> int:
        return int(getattr(self.plan, "estimated_explanation_seconds", getattr(self.plan, "estimated_guide_seconds", 0)))

    @property
    def estimated_observation_seconds(self) -> int:
        return int(self.plan.estimated_observation_seconds)

    @property
    def estimated_interaction_seconds(self) -> int:
        return int(self.plan.estimated_interaction_seconds)

    @property
    def display_name(self) -> str:
        return getattr(self.plan, "display_name", f"{self.requested_minutes}分钟个性化讲解线")

    @property
    def target_minutes(self) -> int:
        return self.requested_minutes

    def to_dict(self) -> dict[str, Any]:
        data = self.plan.to_dict() if isinstance(self.plan, RoutePlan) else asdict(self.plan)
        data.update(
            {
                "route_id": self.route_id,
                "route_strategy": self.route_strategy,
                "requested_minutes": self.requested_minutes,
                "detail_level": self.detail_level,
                "guide_stop_ids": list(self.guide_stop_ids),
                "selection_reason": self.selection_reason,
            }
        )
        return data


@dataclass(frozen=True)
class RouteSelectionResult:
    status: str
    selected: RouteSelection | None
    evaluations: tuple[RouteCandidateEvaluation, ...]
    reason_code: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _detail_policy(detail_level: str) -> tuple[dict[str, float], tuple[float, float], int]:
    policy = _load_json(POLICY_FILE).get("selection_policy", {})
    weights = {name: float(value) for name, value in policy["weights"].items()}
    if abs(sum(weights.values()) - 1.0) > 0.000001:
        raise RouteSelectionError("多目标路线权重必须归一化为 1。")
    try:
        lower, upper = policy["detail_time_bands"][detail_level]
        minimum_stops = int(policy["detail_minimum_guide_stops"][detail_level])
    except KeyError as exc:
        raise RouteSelectionError("未知讲解深度，无法选择路线。") from exc
    return weights, (float(lower), float(upper)), minimum_stops


def _guide_stop_ids(plan: RoutePlan | DynamicRoutePlan) -> tuple[str, ...]:
    return tuple(node_id for node_id in plan.stop_ids if node_id != ENTRY_NODE_ID)


def _node_ornaments() -> dict[str, tuple[dict[str, str], ...]]:
    root = _load_json(NODE_CARDS_FILE)
    indexed: dict[str, tuple[dict[str, str], ...]] = {}
    for card in root.get("cards", []):
        node_id = str(card.get("node_id", ""))
        if not node_id:
            continue
        approved: list[dict[str, str]] = []
        for ornament in card.get("ornaments", []):
            # The card is generated from reviewed mappings.  Still require a
            # matching final node so stale/foreign rows cannot score a route.
            if ornament.get("final_node_id") != node_id:
                continue
            approved.append(
                {
                    "ornament_id": str(ornament.get("ornament_id", "")),
                    "name": str(ornament.get("name", "")),
                    "craft": str(ornament.get("craft", "")),
                }
            )
        indexed[node_id] = tuple(approved)
    return indexed


def derive_interest_coverage(
    guide_stop_ids: tuple[str, ...], interests: list[str] | None,
) -> dict[str, tuple[dict[str, str], ...]]:
    """Return object-level evidence for each explicit interest.

    The function deliberately does not score route titles.  A match must be
    supported by a reviewed object name or craft on one of the actual stops.
    Generic craft-interest words use the same object-level craft evidence.
    """
    index = _node_ornaments()
    evidence: dict[str, tuple[dict[str, str], ...]] = {}
    generic_craft_terms = {"工艺", "装饰", "雕刻", "建筑装饰"}
    for raw_interest in interests or []:
        interest = raw_interest.strip()
        if not interest:
            continue
        matches: list[dict[str, str]] = []
        for node_id in guide_stop_ids:
            for ornament in index.get(node_id, ()):
                name = ornament["name"]
                craft = ornament["craft"]
                if interest in generic_craft_terms:
                    matched = bool(craft)
                    matched_field = "craft"
                else:
                    matched = interest in craft or interest in name
                    matched_field = "craft" if interest in craft else "name"
                if matched:
                    matches.append({"node_id": node_id, **ornament, "matched_field": matched_field})
        evidence[interest] = tuple(matches)
    return evidence


def _time_utilization_score(ratio: float, lower: float, upper: float) -> float:
    midpoint = (lower + upper) / 2
    if lower <= ratio <= upper:
        half_band = max((upper - lower) / 2, 0.000001)
        return 0.9 + 0.1 * (1 - min(abs(ratio - midpoint) / half_band, 1))
    if ratio < lower:
        return max(0.0, 0.9 * ratio / lower)
    return max(0.0, 0.9 * (1 - (ratio - upper) / max(1 - upper, 0.000001)))


def _candidate_components(
    plan: RoutePlan | DynamicRoutePlan,
    route_strategy: str,
    requested_minutes: int,
    interests: list[str],
    detail_level: str,
    weights: dict[str, float],
    time_band: tuple[float, float],
    minimum_stops: int,
) -> tuple[dict[str, float], dict[str, tuple[dict[str, str], ...]]]:
    total = int(plan.estimated_total_seconds or 0)
    budget = requested_minutes * 60
    stop_ids = _guide_stop_ids(plan)
    evidence = derive_interest_coverage(stop_ids, interests)
    coverage = (
        sum(bool(items) for items in evidence.values()) / len(evidence)
        if evidence
        else 0.5
    )
    ratio = total / budget if budget else 0.0
    walk = int(plan.estimated_walk_seconds or 0)
    components = {
        "time_utilization": _time_utilization_score(ratio, *time_band),
        "interest_coverage": coverage,
        "detail_fit": min(1.0, len(stop_ids) / max(minimum_stops, 1)),
        "walking_cost": max(0.0, 1 - walk / max(total, 1)),
        "reviewed_anchor_bonus": 1.0 if route_strategy == "anchor" else 0.0,
    }
    components["total"] = sum(components[name] * weights[name] for name in weights)
    return components, evidence


def _anchor_candidates(available_minutes: int) -> list[tuple[str, RoutePlan]]:
    templates = _load_json(TEMPLATES_FILE).get("templates", [])
    # Reviewed anchors are comparable baselines at their own reviewed target
    # duration. Non-anchor requests (45/75...) remain dynamic compositions.
    return [
        (str(template["route_id"]), plan_template(str(template["route_id"])))
        for template in templates
        if int(template.get("target_minutes", -1)) == available_minutes
    ]


def _select_highest_scored_candidate(
    qualified: list[tuple[RouteCandidateEvaluation, RoutePlan | DynamicRoutePlan]],
) -> tuple[RouteCandidateEvaluation, RoutePlan | DynamicRoutePlan]:
    """Select the highest total-score candidate from all qualified plans.

    Time utilisation is already a normalized scoring component.  It must not
    become an undocumented second eligibility gate: every candidate that is
    within the strict user budget remains comparable here.  Future approved
    anchor-margin policy may deliberately select a near-optimal anchor, but no
    such exception exists in E4-3B1.
    """
    return sorted(
        qualified,
        key=lambda pair: (
            -pair[0].total_score,
            -pair[0].components["time_utilization"],
            -pair[0].components["interest_coverage"],
            -pair[0].components["detail_fit"],
            -pair[0].components["walking_cost"],
            pair[0].candidate_id,
        ),
    )[0]


def recommend_route(
    available_minutes: int,
    interests: list[str] | None = None,
    detail_level: str = "standard",
) -> RouteSelectionResult:
    """Select the best strict-budget reviewed anchor or dynamic route.

    This is the v2 replacement for title-theme-first anchor selection.  It is
    deterministic and purely reads reviewed route/card data.
    """
    interests = sorted({item.strip() for item in (interests or []) if item.strip()})
    weights, time_band, minimum_stops = _detail_policy(detail_level)
    budget_seconds = int(available_minutes) * 60
    raw_candidates: list[tuple[str, str, RoutePlan | DynamicRoutePlan]] = []
    evaluations: list[RouteCandidateEvaluation] = []

    for route_id, plan in _anchor_candidates(available_minutes):
        raw_candidates.append((route_id, "anchor", plan))
    try:
        dynamic = plan_dynamic_route(
            available_minutes=available_minutes,
            interests=interests,
            detail_level=detail_level,
        )
        raw_candidates.append((f"dynamic_{available_minutes}", "dynamic", dynamic))
    except (ValueError, RuntimeError) as exc:
        evaluations.append(
            RouteCandidateEvaluation(
                candidate_id=f"dynamic_{available_minutes}",
                route_strategy="dynamic",
                guide_stop_ids=(),
                estimated_total_seconds=0,
                requested_minutes=available_minutes,
                detail_level=detail_level,
                interest_evidence={},
                components={},
                total_score=0.0,
                rejected_reason=f"dynamic_candidate_unavailable:{exc}",
            )
        )

    qualified: list[tuple[RouteCandidateEvaluation, RoutePlan | DynamicRoutePlan]] = []
    for candidate_id, strategy, plan in raw_candidates:
        total = int(plan.estimated_total_seconds or 0)
        guide_stops = _guide_stop_ids(plan)
        if total <= 0 or total > budget_seconds:
            evaluations.append(
                RouteCandidateEvaluation(
                    candidate_id=candidate_id,
                    route_strategy=strategy,
                    guide_stop_ids=guide_stops,
                    estimated_total_seconds=total,
                    requested_minutes=available_minutes,
                    detail_level=detail_level,
                    interest_evidence={},
                    components={},
                    total_score=0.0,
                    rejected_reason="strict_budget_exceeded_or_unknown",
                )
            )
            continue
        components, evidence = _candidate_components(
            plan, strategy, available_minutes, interests, detail_level,
            weights, time_band, minimum_stops,
        )
        evaluation = RouteCandidateEvaluation(
            candidate_id=candidate_id,
            route_strategy=strategy,
            guide_stop_ids=guide_stops,
            estimated_total_seconds=total,
            requested_minutes=available_minutes,
            detail_level=detail_level,
            interest_evidence=evidence,
            components=components,
            total_score=components["total"],
        )
        evaluations.append(evaluation)
        qualified.append((evaluation, plan))

    if not qualified:
        return RouteSelectionResult(
            status="no_qualified_route",
            selected=None,
            evaluations=tuple(sorted(evaluations, key=lambda item: item.candidate_id)),
            reason_code="no_reviewed_candidate_within_strict_budget",
        )

    # All strict-budget candidates are comparable.  Time-band fit influences
    # their score but is not a hidden rejection rule.
    evaluation, plan = _select_highest_scored_candidate(qualified)
    best_total_score = evaluation.total_score
    evaluations = [
        replace(
            item,
            gap_from_best_score=round(best_total_score - item.total_score, 6),
        ) if item.rejected_reason is None else item
        for item in evaluations
    ]
    reason = {
        "selection_version": "mult_objective_v1",
        "selected_candidate_id": evaluation.candidate_id,
        "route_strategy": evaluation.route_strategy,
        "requested_minutes": available_minutes,
        "detail_level": detail_level,
        "components": evaluation.components,
        "selected_total_score": evaluation.total_score,
        "gap_from_best_score": 0.0,
        "selection_pool_policy": "all_strict_budget_qualified_candidates",
        "qualified_candidate_ids": sorted(item.candidate_id for item, _ in qualified),
        "covered_interests": {
            interest: [item["node_id"] for item in items]
            for interest, items in evaluation.interest_evidence.items()
            if items
        },
        "uncovered_interests": [
            interest for interest, items in evaluation.interest_evidence.items() if not items
        ],
        "strict_budget_seconds": budget_seconds,
        "time_utilization_band": list(time_band),
        "selected_within_target_time_band": (
            time_band[0] <= evaluation.estimated_total_seconds / budget_seconds <= time_band[1]
        ),
    }
    return RouteSelectionResult(
        status="selected",
        selected=RouteSelection(
            plan=plan,
            route_id=evaluation.candidate_id,
            route_strategy=evaluation.route_strategy,
            requested_minutes=available_minutes,
            detail_level=detail_level,
            guide_stop_ids=evaluation.guide_stop_ids,
            selection_reason=reason,
        ),
        evaluations=tuple(sorted(evaluations, key=lambda item: item.candidate_id)),
    )
