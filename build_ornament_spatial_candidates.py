"""Create a reviewable map-node candidate for every ornament location entry.

This is deliberately a conservative text rule matcher.  It never claims that
an architectural direction such as "首进西路北面" is a precise GPS position;
it only links it to the corresponding mapped hall as a candidate for a human
reviewer.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


KNOWLEDGE_FILE = Path("data/chen_clan_academy/knowledge/09_ornament_locations.md")
NODES_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")
OUTPUT_FILE = Path("data/chen_clan_academy/spatial/ornament_spatial_candidates_v0.csv")


# Order matters: more specific locations must be checked first.
LOCATION_RULES = (
    ("中进聚贤堂", "stop_juxian_hall", "high", "mapped guide stop: 中进聚贤堂"),
    ("月台", "label_moon_platform", "high", "mapped platform: 月台"),
    ("前东斋", "label_front_east_study", "high", "mapped room: 前东斋"),
    ("后西厢", "label_rear_west_wing", "high", "mapped wing: 后西厢"),
    ("后进中路", "label_rear_main_hall", "medium", "route alias: 后进中路 → 后进正厅/中厅"),
    ("首进正门", "label_first_main_hall", "medium", "central first-bay candidate"),
    ("首进中路", "label_first_main_hall", "medium", "central first-bay candidate"),
    ("首进西路", "label_first_west_hall", "medium", "west first-bay candidate"),
    ("首进东路", "label_first_east_hall", "medium", "east first-bay candidate"),
    ("中进西路", "label_middle_west_hall", "medium", "west middle-bay candidate"),
    ("中进东路", "label_middle_east_hall", "medium", "east middle-bay candidate"),
    ("后进西路", "label_rear_west_hall", "medium", "west rear-bay candidate"),
    ("后进东路", "label_rear_east_hall", "medium", "east rear-bay candidate"),
)


def parse_entries(path: Path = KNOWLEDGE_FILE) -> list[dict[str, str]]:
    """Read each H2 ornament and its authoritative raw location text."""
    text = path.read_text(encoding="utf-8")
    entries: list[dict[str, str]] = []
    for heading, body in re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        location_match = re.search(r"^- 摆放位置：(.*)$", body, re.M)
        if not location_match:
            continue
        name_match = re.match(r"(.+?)（(.+)）$", heading)
        name, craft = name_match.groups() if name_match else (heading, "")
        entries.append(
            {
                "ornament_name": name,
                "craft": craft,
                "raw_heading": heading,
                "raw_location": location_match.group(1).strip(),
            }
        )
    return entries


def candidate_for_location(raw_location: str) -> tuple[str, str, str, str]:
    """Return node, confidence, rationale and review state for a raw location."""
    for needle, node_id, confidence, rationale in LOCATION_RULES:
        if needle in raw_location:
            state = "review_required" if confidence == "medium" else "candidate_ready"
            return node_id, confidence, rationale, state
    return "", "", "no safe map-node match; add a node or choose one manually", "needs_manual_mapping"


def load_node_names(path: Path = NODES_FILE) -> dict[str, str]:
    """Return the reviewed Chinese display name for every map node."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["node_id"]: row["name"]
            for row in csv.DictReader(handle)
            if row.get("node_id") and row.get("name")
        }


def build_candidates(path: Path = KNOWLEDGE_FILE) -> list[dict[str, str]]:
    node_names = load_node_names()
    rows = []
    for sequence, entry in enumerate(parse_entries(path), start=1):
        node_id, confidence, rationale, review_state = candidate_for_location(entry["raw_location"])
        rows.append(
            {
                "ornament_id": f"orn_{sequence:03d}",
                "source_order": str(sequence),
                **entry,
                "detail_lookup_key": f"{entry['ornament_name']}（{entry['craft']}）",
                "candidate_node_id": node_id,
                "candidate_node_name": node_names.get(node_id, ""),
                "match_confidence": confidence,
                "review_state": review_state,
                "match_rationale": rationale,
                "reviewer_decision": "",
                "final_node_id": "",
                "review_notes": "",
            }
        )
    return rows


def write_candidates(rows: list[dict[str, str]], output: Path = OUTPUT_FILE) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ornament-to-map review candidates.")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    rows = build_candidates()
    write_candidates(rows, args.output)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["review_state"]] = counts.get(row["review_state"], 0) + 1
    print(f"已生成 {len(rows)} 条装饰位置候选：{args.output}")
    print("；".join(f"{state}={count}" for state, count in sorted(counts.items())))


if __name__ == "__main__":
    main()
