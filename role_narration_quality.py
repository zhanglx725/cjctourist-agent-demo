"""Deterministic quality gate for role-narration Shadow evaluations.

This module consumes only bounded audit records. It never calls a model and it
never reads or writes tour state. The resulting report is suitable for Studio
manual evidence, CI fixtures, and a future rollout decision.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from narration_style_policy import approved_style_ids


QUALITY_SCHEMA_VERSION = "role_narration_quality_v1"
SAFETY_REASONS = frozenset({
    "fact_id_boundary_violation",
    "approved_statement_not_preserved",
    "unapproved_fact_trigger",
    "internal_field_leak",
    "unsafe_or_coercive_expression",
    "listen_only_interaction_violation",
    "public_message_boundary_rejected",
})
SCHEMA_REASONS = frozenset({
    "invalid_candidate_schema",
    "invalid_candidate_fields",
    "shadow_input_unavailable",
})


@dataclass(frozen=True)
class RoleNarrationQualityThresholds:
    min_samples_per_style: int = 3
    min_acceptance_rate: float = 0.95
    min_schema_success_rate: float = 0.95
    max_fallback_rate: float = 0.05


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _style_summary(style_id: str, records: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(records)
    accepted = sum(item.get("validation_status") == "accepted" for item in records)
    active_takeovers = sum(bool(item.get("active_takeover")) for item in records)
    fallbacks = sum(bool(item.get("fallback_used")) for item in records)
    state_write_violations = sum(bool(item.get("state_writes")) for item in records)
    legacy_violations = sum(item.get("legacy_message_preserved") is not True for item in records)
    reason_counts: Counter[str] = Counter()
    for item in records:
        reasons = item.get("reason_codes") or []
        if isinstance(reasons, list):
            reason_counts.update(str(reason) for reason in reasons)
    safety_violations = sum(reason_counts[reason] for reason in SAFETY_REASONS)
    schema_failures = sum(reason_counts[reason] for reason in SCHEMA_REASONS)
    return {
        "style_id": style_id,
        "sample_count": total,
        "accepted_count": accepted,
        "acceptance_rate": _rate(accepted, total),
        "schema_success_rate": _rate(total - schema_failures, total),
        "fallback_rate": _rate(fallbacks, total),
        "safety_violation_count": safety_violations,
        "state_write_violation_count": state_write_violations,
        "legacy_message_violation_count": legacy_violations,
        "active_takeover_count": active_takeovers,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def evaluate_role_narration_shadow(
    evaluations: Iterable[Mapping[str, Any]],
    *,
    thresholds: RoleNarrationQualityThresholds | None = None,
) -> dict[str, Any]:
    """Aggregate Shadow audits and fail closed for Active eligibility."""
    limits = thresholds or RoleNarrationQualityThresholds()
    catalog = approved_style_ids()
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unknown_style_count = 0
    malformed_record_count = 0
    for record in evaluations:
        if not isinstance(record, Mapping):
            malformed_record_count += 1
            continue
        style_id = record.get("style_id") or record.get("role_mode")
        if not isinstance(style_id, str):
            malformed_record_count += 1
        elif style_id not in catalog:
            unknown_style_count += 1
        else:
            grouped[style_id].append(record)

    styles = [_style_summary(style_id, grouped[style_id]) for style_id in catalog]
    blockers: list[str] = []
    if malformed_record_count:
        blockers.append("malformed_records")
    if unknown_style_count:
        blockers.append("unknown_styles")
    for item in styles:
        style_id = item["style_id"]
        if item["sample_count"] < limits.min_samples_per_style:
            blockers.append(f"insufficient_samples:{style_id}")
        if item["acceptance_rate"] < limits.min_acceptance_rate:
            blockers.append(f"acceptance_rate:{style_id}")
        if item["schema_success_rate"] < limits.min_schema_success_rate:
            blockers.append(f"schema_success_rate:{style_id}")
        if item["fallback_rate"] > limits.max_fallback_rate:
            blockers.append(f"fallback_rate:{style_id}")
        for field in (
            "safety_violation_count", "state_write_violation_count",
            "legacy_message_violation_count", "active_takeover_count",
        ):
            if item[field]:
                blockers.append(f"{field}:{style_id}")

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "mode": "shadow",
        "catalog_style_count": len(catalog),
        "evaluated_style_count": sum(bool(grouped[style_id]) for style_id in catalog),
        "sample_count": sum(len(values) for values in grouped.values()),
        "malformed_record_count": malformed_record_count,
        "unknown_style_count": unknown_style_count,
        "active_eligible": not blockers,
        "decision": "eligible_for_limited_active" if not blockers else "shadow_only",
        "blockers": blockers,
        "thresholds": {
            "min_samples_per_style": limits.min_samples_per_style,
            "min_acceptance_rate": limits.min_acceptance_rate,
            "min_schema_success_rate": limits.min_schema_success_rate,
            "max_fallback_rate": limits.max_fallback_rate,
        },
        "styles": styles,
    }
