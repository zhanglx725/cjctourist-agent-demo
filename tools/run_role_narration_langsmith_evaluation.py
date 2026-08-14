"""Run and summarize the reviewed LangSmith role-narration evaluation sets.

The runner calls the production graph segment in ``role_narration_langsmith_runner``.
It saves compact audit results locally; LangSmith tracing is opt-in through
``--trace`` and the configured LANGSMITH_PROJECT.  It never changes rollout
configuration, remote datasets, or visitor-facing data.
"""

from __future__ import annotations

import argparse
import json
import traceback
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controlled_rollout import STOP_GUIDANCE_ACTIVE_STYLE_BATCHES
from role_narration_langsmith_runner import run_role_narration_example
from tools.build_role_narration_langsmith_dataset import OUTPUT as BASE_DATASET, load_project_env
from tools.build_role_narration_langsmith_fault_dataset import OUTPUT as FAULT_DATASET

RESULTS_DIR = ROOT / "data" / "chen_clan_academy" / "evaluation" / "langsmith" / "results"
RESULT_SCHEMA_VERSION = "role_narration_stop_guidance_evaluation_result_v1"
QUALITY_FIELDS = ("role_fit", "naturalness", "distinctiveness", "readability")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file is missing: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _compact(case: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    audit = result["commit_audit"]
    validation = result["validation"]
    return {
        "case_id": case["inputs"]["case_id"],
        "style_id": case["inputs"]["style_id"],
        "point_type": case["inputs"].get("point_type", "fault"),
        "failure_type": case["inputs"].get("failure_type"),
        "validation_status": validation.get("validation_status"),
        "validation_reason_codes": validation.get("reason_codes", []),
        "commit_decision": audit.get("commit_decision"),
        "active_takeover": bool(audit.get("active_takeover")),
        "fallback_used": bool(audit.get("fallback_used")),
        "assertions": dict(result["assertions"]),
        "style_quality": dict(result["style_quality"]),
    }


def evaluate_cases(
    cases: Iterable[Mapping[str, Any]], *, trace: bool, style_quality: bool,
    runner: Callable[..., Mapping[str, Any]] = run_role_narration_example,
    checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    records = []
    cases = list(cases)
    for index, case in enumerate(cases, start=1):
        print(f"running_case={index}/{len(cases)}:{case['inputs']['case_id']}", flush=True)
        try:
            result = runner(
                case["inputs"], case.get("outputs"),
                enable_tracing=trace, evaluate_style_quality=style_quality,
            )
            records.append(_compact(case, result))
        except Exception as exc:  # Preserve diagnostic evidence and continue.
            records.append({
                "case_id": case["inputs"]["case_id"],
                "style_id": case["inputs"]["style_id"],
                "point_type": case["inputs"].get("point_type", "fault"),
                "failure_type": case["inputs"].get("failure_type"),
                "execution_error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=6),
                "assertions": {"runner_completed": False},
                "style_quality": {"status": "not_run"},
            })
        if checkpoint:
            checkpoint(records)
    return records


def _assertions_pass(record: Mapping[str, Any]) -> bool:
    return all(bool(value) for value in record["assertions"].values())


def summarize(base_records: list[Mapping[str, Any]], fault_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in base_records:
        grouped[str(item["style_id"])].append(item)
    batches = []
    for number, style_ids in enumerate(STOP_GUIDANCE_ACTIVE_STYLE_BATCHES, start=1):
        records = [record for style_id in style_ids for record in grouped[style_id]]
        batches.append({
            "batch": number, "style_ids": list(style_ids), "case_count": len(records),
            "deterministic_pass_count": sum(_assertions_pass(record) for record in records),
            "deterministic_passed": bool(records) and all(_assertions_pass(record) for record in records),
        })
    scored = [record["style_quality"] for record in base_records if record["style_quality"].get("status") == "scored"]
    quality_values = [score[field] for score in scored for field in QUALITY_FIELDS]
    quality_gate = bool(scored) and len(scored) == len(base_records) and all(value >= 1 for value in quality_values) and (
        sum(quality_values) / len(quality_values) >= 1.5
    )
    fault_gate = bool(fault_records) and all(
        _assertions_pass(record)
        and record["fallback_used"]
        and not record["active_takeover"]
        and record["commit_decision"] == "legacy_fallback_published"
        for record in fault_records
    )
    # A single rollout batch is useful evidence, but it must never be
    # presented as the 54-case release gate.
    complete_base_matrix = len(base_records) == 54
    deterministic_gate = complete_base_matrix and all(_assertions_pass(record) for record in base_records)
    return {
        "base_case_count": len(base_records),
        "fault_case_count": len(fault_records),
        "batches": batches,
        "quality": {
            "scored_case_count": len(scored),
            "required_scored_case_count": len(base_records),
            "metric_minimum": min(quality_values) if quality_values else None,
            "metric_average": round(sum(quality_values) / len(quality_values), 3) if quality_values else None,
            "gate": "each metric >= 1; all 54 cases scored; overall metric average >= 1.5",
            "passed": quality_gate,
        },
        "gates": {
            "deterministic_54_of_54": deterministic_gate,
            "base_matrix_complete_54_of_54": complete_base_matrix,
            "style_quality": quality_gate,
            "fault_fallback_12_of_12": fault_gate,
            "release_eligible": deterministic_gate and quality_gate and fault_gate,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, choices=range(1, 4), help="Run one configured style batch")
    parser.add_argument("--faults", action="store_true", help="Also run all 12 deterministic fault cases")
    parser.add_argument("--resume-checkpoint", type=Path, help="Resume base cases saved by a prior checkpoint")
    parser.add_argument("--trace", action="store_true", help="Allow LangSmith tracing for live model/judge calls")
    parser.add_argument("--no-style-quality", action="store_true", help="Skip LLM expression judge (cannot pass release gate)")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if a release gate fails")
    args = parser.parse_args()
    load_project_env()
    base_cases = load_jsonl(BASE_DATASET)
    if len(base_cases) != 54:
        raise RuntimeError(f"Expected 54 base cases, got {len(base_cases)}")
    selected = base_cases
    if args.batch:
        styles = set(STOP_GUIDANCE_ACTIVE_STYLE_BATCHES[args.batch - 1])
        selected = [case for case in base_cases if case["inputs"]["style_id"] in styles]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    completed_records: list[dict[str, Any]] = []
    if args.resume_checkpoint:
        saved = json.loads(args.resume_checkpoint.read_text(encoding="utf-8"))
        completed_records = list(saved.get("records", []))
        expected_ids = {case["inputs"]["case_id"] for case in selected}
        if any(record.get("case_id") not in expected_ids for record in completed_records):
            raise RuntimeError("Checkpoint does not match the selected evaluation batch")
    completed_ids = {record["case_id"] for record in completed_records}
    remaining = [case for case in selected if case["inputs"]["case_id"] not in completed_ids]
    checkpoint_file = RESULTS_DIR / (
        f"role_narration_stop_guidance_eval_checkpoint_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    )
    def save_checkpoint(records: list[dict[str, Any]]) -> None:
        checkpoint_file.write_text(
            json.dumps({"records": [*completed_records, *records]}, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    new_records = evaluate_cases(
        remaining, trace=args.trace, style_quality=not args.no_style_quality, checkpoint=save_checkpoint,
    )
    base_records = [*completed_records, *new_records]
    fault_records = evaluate_cases(
        load_jsonl(FAULT_DATASET), trace=args.trace, style_quality=False, checkpoint=save_checkpoint,
    ) if args.faults else []
    summary = summarize(base_records, fault_records)
    payload = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "evaluation_entry": "production_role_narration_graph_segment",
        "full_stop_guidance_session": False,
        "tracing_requested": args.trace,
        "base_dataset": str(BASE_DATASET),
        "fault_dataset": str(FAULT_DATASET) if args.faults else None,
        "summary": summary,
        "base_records": base_records,
        "fault_records": fault_records,
    }
    output = RESULTS_DIR / f"role_narration_stop_guidance_eval_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result_file={output}", flush=True)
    print(f"base_cases={len(base_records)}", flush=True)
    print(f"fault_cases={len(fault_records)}", flush=True)
    print(f"release_eligible={summary['gates']['release_eligible']}", flush=True)
    if args.strict and not summary["gates"]["release_eligible"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
