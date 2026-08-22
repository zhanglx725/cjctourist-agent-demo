"""Merge independently executed role-narration batches into one release audit."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_role_narration_langsmith_evaluation import RESULTS_DIR, RESULT_SCHEMA_VERSION, summarize


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported result schema: {path}")
    return value


def _unique(records: list[dict], label: str) -> list[dict]:
    ids = [record["case_id"] for record in records]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label} case IDs: {', '.join(duplicates)}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-result", type=Path, action="append", required=True)
    parser.add_argument("--fault-result", type=Path, required=True)
    args = parser.parse_args()
    base_sources = [_read(path) for path in args.base_result]
    fault_source = _read(args.fault_result)
    base_records = _unique([record for source in base_sources for record in source["base_records"]], "base")
    fault_records = _unique(list(fault_source["fault_records"]), "fault")
    summary = summarize(base_records, fault_records)
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_entry": "production_role_narration_graph_segment",
        "full_stop_guidance_session": False,
        "aggregation": True,
        "source_result_files": [str(path) for path in args.base_result],
        "fault_source_result_file": str(args.fault_result),
        "summary": summary,
        "base_records": base_records,
        "fault_records": fault_records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / "role_narration_stop_guidance_eval_v1_aggregated.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result_file={output}")
    print(f"base_cases={len(base_records)}")
    print(f"fault_cases={len(fault_records)}")
    print(f"release_eligible={summary['gates']['release_eligible']}")


if __name__ == "__main__":
    main()
