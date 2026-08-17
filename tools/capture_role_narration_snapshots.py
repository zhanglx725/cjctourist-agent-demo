"""Capture comparable Active visitor-text snapshots for selected role styles.

This is an evidence tool, not a rollout switch: it calls the existing
production role-narration graph segment and writes a local JSON artifact.  A
candidate API can be compared by changing only the role-model environment
configuration and using a different provider label.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from role_narration_langsmith_runner import run_role_narration_example
from tools.build_role_narration_langsmith_dataset import build_examples, load_project_env


DEFAULT_STYLES = (
    "ancient_scholar",
    "bestie_chat",
    "buddy_guide",
    "exploration_game",
)
OUTPUT_DIR = ROOT / "data" / "chen_clan_academy" / "evaluation" / "snapshots"
SCHEMA_VERSION = "role_narration_snapshot_v1"


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _file_label(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in value.strip()
    ).strip("._")
    return normalized or "provider"


def build_snapshot_cases(style_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Select the three reviewed point types for each requested style."""
    requested = tuple(dict.fromkeys(style_ids))
    available = build_examples()
    known = {str(item["inputs"]["style_id"]) for item in available}
    unknown = sorted(set(requested) - known)
    if unknown:
        raise ValueError(f"Unknown or unapproved style IDs: {', '.join(unknown)}")
    selected = [
        item for item in available
        if str(item["inputs"]["style_id"]) in requested
    ]
    order = {style_id: index for index, style_id in enumerate(requested)}
    return sorted(
        selected,
        key=lambda item: (order[str(item["inputs"]["style_id"])], str(item["inputs"]["point_type"])),
    )


def capture(
    cases: Iterable[Mapping[str, Any]], *, provider_label: str,
) -> list[dict[str, Any]]:
    records = []
    # A style's three reviewed point types simulate three consecutive stops in
    # one visitor thread. This makes the snapshot measure real recurrence
    # protection instead of treating every sample as a first encounter.
    recent_by_style: dict[str, tuple[str, ...]] = {}
    for case in cases:
        style_id = str(case["inputs"]["style_id"])
        result = run_role_narration_example(
            case["inputs"], case.get("outputs"), enable_tracing=False,
            evaluate_style_quality=False, natural_full=True,
            recent_discourse_expressions=recent_by_style.get(style_id, ()),
        )
        recent_by_style[style_id] = tuple(
            value for value in result.get("role_discourse_recent_expressions", [])
            if isinstance(value, str) and value.strip()
        )[-12:]
        records.append({
            "case_id": case["inputs"]["case_id"],
            "style_id": case["inputs"]["style_id"],
            "point_type": case["inputs"]["point_type"],
            "provider_label": provider_label,
            "final_visitor_message": result["final_visitor_message"],
            "active_takeover": bool(result["commit_audit"].get("active_takeover")),
            "fallback_used": bool(result["commit_audit"].get("fallback_used")),
            "natural_component_fallback_used": bool(
                result["commit_audit"].get("natural_component_fallback_used")
            ),
            "model_called": bool(result["commit_audit"].get("model_called")),
            "generation_reason_code": result["candidate"].get("reason_code"),
            "validation_status": result["validation"].get("validation_status"),
            "validation_reason_codes": result["validation"].get("reason_codes", []),
            "assertions": result["assertions"],
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--styles", nargs="+", default=list(DEFAULT_STYLES),
        help="Approved style IDs; defaults to the four contrast styles.",
    )
    parser.add_argument(
        "--provider-label", default=os.getenv("ROLE_NARRATION_MODEL", "current"),
        help="Human-readable provider/model label stored in the artifact.",
    )
    args = parser.parse_args()
    load_project_env()
    required = (
        "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED",
        "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED",
    )
    missing = [name for name in required if not _enabled(name)]
    if missing:
        raise RuntimeError(
            "Snapshots require real natural narration; set " + ", ".join(missing) + "=true"
        )
    cases = build_snapshot_cases(args.styles)
    records = capture(cases, provider_label=args.provider_label)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / (
        f"role_narration_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{_file_label(args.provider_label)}.json"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "continuity_mode": "per_style_thread",
        "generated_at": datetime.now(UTC).isoformat(),
        "styles": list(dict.fromkeys(args.styles)),
        "provider_label": args.provider_label,
        "records": records,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"snapshot_file={output}")
    print(f"record_count={len(records)}")
    print(f"active_takeover_count={sum(item['active_takeover'] for item in records)}")
    print(f"fallback_count={sum(item['fallback_used'] for item in records)}")
    print(
        "natural_component_fallback_count="
        f"{sum(item['natural_component_fallback_used'] for item in records)}"
    )
    model_unavailable_count = sum(
        str(item.get("generation_reason_code") or "").startswith(
            "natural_discourse_fallback:model_unavailable:"
        )
        for item in records
    )
    print(f"model_unavailable_count={model_unavailable_count}")
    assertion_failure_count = sum(
        not all(bool(value) for value in item["assertions"].values())
        for item in records
    )
    print(f"assertion_failure_count={assertion_failure_count}")
    if assertion_failure_count:
        raise RuntimeError(
            "Snapshot contains graph-contract assertion failures; inspect the saved artifact."
        )
    if model_unavailable_count:
        raise RuntimeError(
            "Role-model provider was unavailable; this snapshot is not valid for API comparison."
        )


if __name__ == "__main__":
    main()
