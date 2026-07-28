"""Benchmark reviewed anchors and dynamic composition under E4-3B selection.

This module is an evaluation layer only.  It neither edits space data nor
calls an LLM. Its output retains the anchor comparison baseline while using the
same strict-budget multi-objective selector as route initialization.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from dynamic_route_planner import (
    DynamicRoutePlan,
    eligible_dynamic_stops,
    plan_dynamic_route,
    score_candidate,
)
from route_planner import RoutePlan, plan_template, recommend_route


CASES_FILE = Path("data/chen_clan_academy/routes/route_benchmark_cases_v1.json")


@dataclass(frozen=True)
class RouteBenchmarkResult:
    case_id: str
    available_minutes: int
    interests: tuple[str, ...]
    recommended_strategy: str
    reason_codes: tuple[str, ...]
    dynamic_stop_ids: tuple[str, ...]
    dynamic_total_seconds: int
    dynamic_allowed_seconds: int
    dynamic_within_budget: bool
    anchor_route_id: str | None
    anchor_stop_ids: tuple[str, ...]
    anchor_total_seconds: int | None
    anchor_within_budget: bool | None
    anchor_stop_overlap: float | None
    anchor_key_stop_coverage: float | None
    dynamic_interest_score: float
    anchor_interest_score: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def load_benchmark_cases(path: Path = CASES_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _guide_stops(route: RoutePlan) -> tuple[str, ...]:
    # The entry node is an arrival context, rather than a formal guide stop.
    return tuple(node_id for node_id in route.stop_ids if node_id != "entrance_main_outside")


def _interest_score(stop_ids: tuple[str, ...], interests: list[str]) -> float:
    candidates = {item.node_id: item for item in eligible_dynamic_stops()}
    selected = []
    total = 0.0
    for node_id in stop_ids:
        candidate = candidates.get(node_id)
        if candidate is None:
            continue
        total += score_candidate(candidate, interests, selected).total
        selected.append(candidate)
    return round(total, 2)


def evaluate_benchmark_case(case: dict) -> RouteBenchmarkResult:
    """Evaluate one reviewed benchmark case without changing recommendation code."""
    minutes = int(case["available_minutes"])
    interests = list(case.get("interests", []))
    detail_level = str(case.get("detail_level", "standard"))
    dynamic: DynamicRoutePlan = plan_dynamic_route(minutes, interests, detail_level=detail_level)
    dynamic_score = _interest_score(dynamic.stop_ids, interests)
    selected_result = recommend_route(minutes, interests, detail_level=detail_level)
    if selected_result.selected is None:
        raise ValueError("基准案例在严格时间预算内没有可用审核路线。")
    selected = selected_result.selected
    anchor_id = case.get("anchor_route_id")
    if not anchor_id:
        return RouteBenchmarkResult(
            case_id=case["case_id"],
            available_minutes=minutes,
            interests=tuple(interests),
            recommended_strategy=selected.route_strategy,
            reason_codes=("mult_objective_selection", "strict_budget"),
            dynamic_stop_ids=dynamic.stop_ids,
            dynamic_total_seconds=dynamic.estimated_total_seconds,
            dynamic_allowed_seconds=dynamic.allowed_total_seconds,
            dynamic_within_budget=dynamic.estimated_total_seconds <= dynamic.allowed_total_seconds,
            anchor_route_id=None,
            anchor_stop_ids=(),
            anchor_total_seconds=None,
            anchor_within_budget=None,
            anchor_stop_overlap=None,
            anchor_key_stop_coverage=None,
            dynamic_interest_score=dynamic_score,
            anchor_interest_score=None,
        )

    anchor = plan_template(anchor_id)
    anchor_stops = _guide_stops(anchor)
    anchor_score = _interest_score(anchor_stops, interests)
    dynamic_set = set(dynamic.stop_ids)
    anchor_set = set(anchor_stops)
    overlap = len(dynamic_set.intersection(anchor_set)) / len(dynamic_set.union(anchor_set))
    key_stops = set(case.get("anchor_key_stop_ids", []))
    key_coverage = len(dynamic_set.intersection(key_stops)) / len(key_stops) if key_stops else 1.0

    reasons = ["mult_objective_selection", "strict_budget"]
    if selected.route_strategy == "anchor":
        reasons.append("reviewed_anchor_selected")
    else:
        reasons.append("dynamic_selected_after_candidate_evaluation")

    return RouteBenchmarkResult(
        case_id=case["case_id"],
        available_minutes=minutes,
        interests=tuple(interests),
        recommended_strategy=selected.route_strategy,
        reason_codes=tuple(reasons),
        dynamic_stop_ids=dynamic.stop_ids,
        dynamic_total_seconds=dynamic.estimated_total_seconds,
        dynamic_allowed_seconds=dynamic.allowed_total_seconds,
        dynamic_within_budget=dynamic.estimated_total_seconds <= dynamic.allowed_total_seconds,
        anchor_route_id=anchor_id,
        anchor_stop_ids=anchor_stops,
        anchor_total_seconds=anchor.estimated_total_seconds,
        anchor_within_budget=(anchor.estimated_total_seconds or 0) <= minutes * 60,
        anchor_stop_overlap=round(overlap, 3),
        anchor_key_stop_coverage=round(key_coverage, 3),
        dynamic_interest_score=dynamic_score,
        anchor_interest_score=anchor_score,
    )


def run_benchmark_cases(path: Path = CASES_FILE) -> list[RouteBenchmarkResult]:
    return [evaluate_benchmark_case(case) for case in load_benchmark_cases(path)]


def main() -> None:
    for result in run_benchmark_cases():
        anchor = result.anchor_route_id or "-"
        print(
            f"{result.case_id}: strategy={result.recommended_strategy} "
            f"| anchor={anchor} | dynamic={len(result.dynamic_stop_ids)} stops "
            f"| dynamic_time={result.dynamic_total_seconds}/{result.dynamic_allowed_seconds}s"
        )
        print(f"  reasons={','.join(result.reason_codes)}")
        if result.anchor_route_id:
            print(
                f"  overlap={result.anchor_stop_overlap:.1%} "
                f"| key_coverage={result.anchor_key_stop_coverage:.1%} "
                f"| interest(dynamic/anchor)={result.dynamic_interest_score}/{result.anchor_interest_score}"
            )


if __name__ == "__main__":
    main()
