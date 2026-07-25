"""Import manually reviewed ornament-to-space mappings from the team workbook.

The reviewer workbook is the editable source.  This script produces the
machine-readable mapping consumed by future route and guide functions.  It
reads the XLSX Open XML files with only the Python standard library so every
team member can run it inside the existing virtual environment.
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
SPATIAL_DIR = ROOT / "data" / "chen_clan_academy" / "spatial"
DEFAULT_WORKBOOK = ROOT / "ornament_spatial_candidates_v1.xlsx"
DEFAULT_OUTPUT = SPATIAL_DIR / "ornament_spatial_mapping_v1.csv"
NODES_FILE = SPATIAL_DIR / "marker_inventory_v0.csv"
ADD_NODE_REGISTRY = SPATIAL_DIR / "add_node_registry_v0.csv"

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def column_name(cell_ref: str) -> str:
    """Return the alphabetical column part of an Excel reference (e.g. A12)."""
    return re.sub(r"\d+", "", cell_ref)


def read_xlsx_rows(path: Path) -> list[dict[str, str]]:
    """Read the first worksheet as rows keyed by its header row."""
    with zipfile.ZipFile(path) as workbook:
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared_strings = ["".join(item.itertext()) for item in shared_root]
        sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    raw_rows: list[dict[str, str]] = []
    for row in sheet_root.findall(f".//{MAIN_NS}sheetData/{MAIN_NS}row"):
        values: dict[str, str] = {}
        for cell in row.findall(f"{MAIN_NS}c"):
            value = cell.find(f"{MAIN_NS}v")
            if value is None:
                rendered = ""
            elif cell.attrib.get("t") == "s":
                rendered = shared_strings[int(value.text or "0")]
            else:
                rendered = value.text or ""
            values[column_name(cell.attrib["r"])] = rendered.strip()
        raw_rows.append(values)

    if not raw_rows:
        return []
    headers = raw_rows[0]
    return [
        {headers[column]: value for column, value in row.items() if column in headers}
        for row in raw_rows[1:]
        if row.get("A", "").strip()
    ]


def read_node_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["node_id"] for row in csv.DictReader(handle)}


def read_add_node_registry(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["add_node_key"].strip(): row["node_id"].strip()
            for row in csv.DictReader(handle)
        }


def normalise_decision(value: str) -> str:
    """Normalise add_node variants introduced by different Excel editors."""
    decision = value.strip().strip("`'").lower().replace(" ", "")
    if decision in {"add_node", "add_nodes"}:
        return "add_node"
    return decision


def new_node_key(review_notes: str) -> str:
    """Use the name before the first Chinese/English comma as the node key."""
    return re.split(r"[，,]", review_notes.strip(), maxsplit=1)[0].strip()


def build_mapping_rows(
    reviewed_rows: list[dict[str, str]], node_ids: set[str], add_nodes: dict[str, str]
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in reviewed_rows:
        decision = normalise_decision(row.get("reviewer_decision", ""))
        ornament_id = row.get("ornament_id", "").strip()
        if not ornament_id:
            continue

        if decision == "change":
            final_node_id = row.get("final_node_id", "").strip()
            source = "manual_review_existing_node"
        elif decision == "add_node":
            key = new_node_key(row.get("review_notes", ""))
            if key not in add_nodes:
                raise ValueError(
                    f"{ornament_id} requests new node '{key}', but it is not in "
                    f"{ADD_NODE_REGISTRY.name}. Add/reuse the node before importing."
                )
            final_node_id = add_nodes[key]
            source = "manual_review_registered_add_node"
        else:
            raise ValueError(
                f"{ornament_id} has unsupported reviewer_decision "
                f"'{row.get('reviewer_decision', '')}'. Use change or add_node."
            )

        if final_node_id not in node_ids:
            raise ValueError(
                f"{ornament_id} points to unknown node_id '{final_node_id}'. "
                "Check marker_inventory_v0.csv."
            )

        output.append(
            {
                "ornament_id": ornament_id,
                "ornament_name": row.get("ornament_name", "").strip(),
                "craft": row.get("craft", "").strip(),
                "raw_location": row.get("raw_location", "").strip(),
                "final_node_id": final_node_id,
                "mapping_decision": decision,
                "mapping_source": source,
                "review_notes": row.get("review_notes", "").strip(),
            }
        )
    return output


def write_mapping(rows: list[dict[str, str]], output: Path) -> None:
    fields = [
        "ornament_id",
        "ornament_name",
        "craft",
        "raw_location",
        "final_node_id",
        "mapping_decision",
        "mapping_source",
        "review_notes",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import reviewed ornament spatial mappings.")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = build_mapping_rows(
        read_xlsx_rows(args.workbook),
        read_node_ids(NODES_FILE),
        read_add_node_registry(ADD_NODE_REGISTRY),
    )
    if len(rows) != 105:
        raise ValueError(f"Expected 105 reviewed ornament rows, received {len(rows)}.")
    write_mapping(rows, args.output)
    print(f"已导入 {len(rows)} 条文物—点位关联：{args.output}")


if __name__ == "__main__":
    main()
