"""Benchmark reviewed anchor routes against deterministic dynamic composition.

This module is an evaluation layer only.  It neither edits space data nor
calls an LLM.  Its output gives reviewers an explicit reason for retaining a
30/60/90-minute human-reviewed anchor route or using dynamic composition for
non-anchor durations.
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
from route_planner import RoutePlan, plan_template


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
    dynamic: DynamicRoutePlan = plan_dynamic_route(minutes, interests)
    dynamic_score = _interest_score(dynamic.stop_ids, interests)
    anchor_id = case.get("anchor_route_id")
    if not anchor_id:
        return RouteBenchmarkResult(
            case_id=case["case_id"],
            available_minutes=minutes,
            interests=tuple(interests),
            recommended_strategy="dynamic",
            reason_codes=("non_anchor_duration", "dynamic_within_budget"),
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

    # Human-reviewed anchors represent deliberate narrative coverage.  For an
    # exact 30/60/90 request, retain the anchor if dynamic composition omits a
    # designated anchor highlight or fails its time budget.  A later review may
    # loosen this policy only after comparable dynamic routes are approved.
    reasons: list[str] = []
    if dynamic.estimated_total_seconds > dynamic.allowed_total_seconds:
        reasons.append("dynamic_over_budget")
    if key_coverage < 1.0:
        reasons.append("dynamic_misses_anchor_key_stop")
    if overlap < 0.5:
        reasons.append("dynamic_low_anchor_overlap")
    if dynamic_score < anchor_score:
        reasons.append("dynamic_lower_interest_score")
    strategy = "anchor" if reasons else "dynamic"
    if strategy == "anchor":
        reasons.insert(0, "reviewed_anchor_fallback")
    else:
        reasons.append("dynamic_matches_anchor_baseline")

    return RouteBenchmarkResult(
        case_id=case["case_id"],
        available_minutes=minutes,
        interests=tuple(interests),
        recommended_strategy=strategy,
        reason_codes=tuple(reasons),
        dynamic_stop_ids=dynamic.stop_ids,
        dynamic_total_seconds=dynamic.estimated_total_seconds,
        dynamic_allowed_seconds=dynamic.allowed_total_seconds,
        dynamic_within_budget=dynamic.estimated_total_seconds <= dynamic.allowed_total_seconds,
        anchor_route_id=anchor_id,
        anchor_stop_ids=anchor_stops,
        anchor_total_seconds=anchor.estimated_total_seconds,
        anchor_within_budget=bool(anchor.within_time_budget),
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
