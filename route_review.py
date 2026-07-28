"""Build an A0-6 human-review report from route benchmark results.

The report separates automatic safety/consistency checks from questions that
must be judged by a person on site or against the official map.  It is not an
LLM evaluation and does not alter the route-selection policy.
"""

from __future__ import annotations

import json
import csv
from collections import Counter
from pathlib import Path

from dynamic_route_planner import eligible_dynamic_stops, plan_dynamic_route
from route_benchmark import RouteBenchmarkResult, run_benchmark_cases
from route_planner import plan_template


JSON_OUTPUT_FILE = Path("data/chen_clan_academy/routes/route_review_results_v1.json")
CSV_OUTPUT_FILE = Path("data/chen_clan_academy/routes/route_review_results_v1.csv")


def _repeated(values: tuple[str, ...]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _route_payload(result: RouteBenchmarkResult) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], int, int]:
    """Return the route chosen by benchmark policy in a uniform shape."""
    if result.recommended_strategy == "anchor":
        plan = plan_template(result.anchor_route_id or "")
        guide_stops = tuple(node for node in plan.stop_ids if node != "entrance_main_outside")
        return (
            f"anchor:{plan.route_id}",
            guide_stops,
            plan.full_path_node_ids,
            plan.edge_ids,
            plan.estimated_total_seconds or 0,
            plan.target_minutes * 60,
        )
    plan = plan_dynamic_route(result.available_minutes, list(result.interests))
    return (
        "dynamic",
        plan.stop_ids,
        plan.full_path_node_ids,
        plan.edge_ids,
        plan.estimated_total_seconds,
        plan.allowed_total_seconds,
    )


def build_review_records() -> list[dict]:
    """Build records ready for reviewers to approve, revise or reject."""
    candidates = {item.node_id: item for item in eligible_dynamic_stops()}
    records: list[dict] = []
    for result in run_benchmark_cases():
        source, stop_ids, path_ids, edge_ids, total, allowed = _route_payload(result)
        guide_candidates = [candidates[node_id] for node_id in stop_ids if node_id in candidates]
        theme_counts = Counter(theme for item in guide_candidates for theme in item.themes)
        repeated_themes = sorted(theme for theme, count in theme_counts.items() if count > 1)
        repeated_edges = _repeated(edge_ids)
        records.append(
            {
                "case_id": result.case_id,
                "requested_minutes": result.available_minutes,
                "interests": list(result.interests),
                "recommended_strategy": result.recommended_strategy,
                "selection_reason_codes": list(result.reason_codes),
                "chosen_route_source": source,
                "guide_stop_ids": list(stop_ids),
                "guide_stop_names": [candidates[node_id].display_name for node_id in stop_ids if node_id in candidates],
                "full_path_node_ids": list(path_ids),
                "edge_ids": list(edge_ids),
                "time_seconds": {
                    "estimated_total": total,
                    "allowed_upper_bound": allowed,
                    "within_budget": total <= allowed,
                    "budget_utilization": round(total / allowed, 3) if allowed else None,
                },
                "automatic_checks": {
                    "all_guide_stops_are_reviewed_and_ornament_rich": len(guide_candidates) == len(stop_ids),
                    "repeated_guide_stop_ids": _repeated(stop_ids),
                    "repeated_edge_ids": repeated_edges,
                    "theme_repeat_candidates": repeated_themes,
                    "anchor_key_stop_coverage": result.anchor_key_stop_coverage,
                    "dynamic_anchor_stop_overlap": result.anchor_stop_overlap,
                    "path_returns_to_front_courtyard_exit_area": path_ids[-1] == "stop_front_courtyard_center",
                },
                "manual_review": {
                    "status": "pending",
                    "guide_value": "pending",
                    "walking_order_natural": "pending",
                    "meaningless_backtracking": "pending",
                    "theme_repetition_acceptable": "pending",
                    "time_budget_feels_realistic": "pending",
                    "reviewer": "",
                    "reviewed_at": "",
                    "notes": ""
                },
            }
        )
    return records


def write_review_report(output: Path = JSON_OUTPUT_FILE) -> Path:
    payload = {
        "schema_version": "v1",
        "status": "pending_human_review",
        "instructions": "Only edit manual_review fields after reviewing against the official map or on site. Do not change node IDs in this file.",
        "records": build_review_records(),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def write_review_csv(output: Path = CSV_OUTPUT_FILE) -> Path:
    """Write a flat Excel-friendly review sheet without losing the JSON source."""
    fieldnames = [
        "case_id", "requested_minutes", "interests", "recommended_strategy",
        "chosen_route_source", "guide_stop_names", "estimated_total_seconds",
        "allowed_upper_bound_seconds", "within_budget", "repeated_guide_stop_ids",
        "repeated_edge_ids", "theme_repeat_candidates", "anchor_key_stop_coverage",
        "dynamic_anchor_stop_overlap", "manual_status", "guide_value",
        "walking_order_natural", "meaningless_backtracking",
        "theme_repetition_acceptable", "time_budget_feels_realistic", "reviewer",
        "reviewed_at", "notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in build_review_records():
            checks = record["automatic_checks"]
            manual = record["manual_review"]
            writer.writerow({
                "case_id": record["case_id"],
                "requested_minutes": record["requested_minutes"],
                "interests": ";".join(record["interests"]),
                "recommended_strategy": record["recommended_strategy"],
                "chosen_route_source": record["chosen_route_source"],
                "guide_stop_names": " → ".join(record["guide_stop_names"]),
                "estimated_total_seconds": record["time_seconds"]["estimated_total"],
                "allowed_upper_bound_seconds": record["time_seconds"]["allowed_upper_bound"],
                "within_budget": record["time_seconds"]["within_budget"],
                "repeated_guide_stop_ids": ";".join(checks["repeated_guide_stop_ids"]),
                "repeated_edge_ids": ";".join(checks["repeated_edge_ids"]),
                "theme_repeat_candidates": ";".join(checks["theme_repeat_candidates"]),
                "anchor_key_stop_coverage": checks["anchor_key_stop_coverage"],
                "dynamic_anchor_stop_overlap": checks["dynamic_anchor_stop_overlap"],
                "manual_status": manual["status"],
                "guide_value": manual["guide_value"],
                "walking_order_natural": manual["walking_order_natural"],
                "meaningless_backtracking": manual["meaningless_backtracking"],
                "theme_repetition_acceptable": manual["theme_repetition_acceptable"],
                "time_budget_feels_realistic": manual["time_budget_feels_realistic"],
                "reviewer": manual["reviewer"],
                "reviewed_at": manual["reviewed_at"],
                "notes": manual["notes"],
            })
    return output


def main() -> None:
    json_output = write_review_report()
    csv_output = write_review_csv()
    print(f"Generated {len(build_review_records())} A0-6 review records: {json_output}")
    print(f"Excel-friendly review sheet: {csv_output}")


if __name__ == "__main__":
    main()
