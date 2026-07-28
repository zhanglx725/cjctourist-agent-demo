"""Read-only score-truth inspection for E4-3B policy calibration.

This script does not alter route selection, route data, or application state.
Run it with the project virtual-environment interpreter before choosing the
``anchor_preference_margin`` policy value.
"""

from __future__ import annotations

import json

from route_selection import recommend_route


SCENARIOS = (
    ("30m_plaster_standard", 30, ["灰塑"], "standard"),
    ("60m_plaster_wood_standard", 60, ["灰塑", "木雕"], "standard"),
    ("90m_plaster_wood_deep", 90, ["灰塑", "木雕"], "deep"),
    ("45m_plaster_standard", 45, ["灰塑"], "standard"),
    ("75m_plaster_wood_standard", 75, ["灰塑", "木雕"], "standard"),
)


def inspect_scenario(
    case_id: str,
    available_minutes: int,
    interests: list[str],
    detail_level: str,
) -> dict[str, object]:
    """Return only auditable selector outputs for one fixed calibration case."""
    result = recommend_route(available_minutes, interests, detail_level)
    candidates = []
    for item in result.evaluations:
        total_seconds = item.estimated_total_seconds
        candidates.append(
            {
                "candidate_id": item.candidate_id,
                "route_strategy": item.route_strategy,
                "guide_stop_ids": list(item.guide_stop_ids),
                "estimated_total_seconds": total_seconds,
                "budget_utilization": round(
                    total_seconds / (available_minutes * 60), 4
                ) if total_seconds else None,
                "components": item.components,
                "interest_coverage": {
                    interest: len(matches)
                    for interest, matches in item.interest_evidence.items()
                },
                "total_score": item.total_score if item.rejected_reason is None else None,
                "gap_from_best_score": item.gap_from_best_score
                if item.rejected_reason is None
                else None,
                "rejected_reason": item.rejected_reason,
            }
        )
    return {
        "case_id": case_id,
        "available_minutes": available_minutes,
        "interests": interests,
        "detail_level": detail_level,
        "selection_status": result.status,
        "selected_route_id": result.selected.route_id if result.selected else None,
        "selected_strategy": result.selected.route_strategy if result.selected else None,
        "candidates": candidates,
    }


def main() -> None:
    report = [inspect_scenario(*scenario) for scenario in SCENARIOS]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
