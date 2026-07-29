"""Small deterministic calculations over already verified evidence operands.

This module does not retrieve facts and never asks an LLM to supply an operand.
Callers must first extract both operands from evidence in the reviewed category.
Missing, non-numeric, or inconsistent operands fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any, Iterable


class ControlledDerivationError(ValueError):
    """Raised when a deterministic derivation cannot be safely completed."""


@dataclass(frozen=True)
class DerivedOperand:
    """A value whose evidence provenance was verified by the caller."""

    label: str
    value: Real
    evidence_indexes: tuple[int, ...]


def deterministic_difference(
    *,
    operation: str,
    start: DerivedOperand,
    end: DerivedOperand,
    unit: str,
) -> dict[str, Any]:
    """Return a time/quantity difference without model inference."""

    if operation not in {"time_difference", "quantity_difference"}:
        raise ControlledDerivationError(f"unsupported operation: {operation}")
    if not start.evidence_indexes or not end.evidence_indexes:
        raise ControlledDerivationError("both operands require evidence")
    if not isinstance(start.value, Real) or isinstance(start.value, bool):
        raise ControlledDerivationError("start operand must be numeric")
    if not isinstance(end.value, Real) or isinstance(end.value, bool):
        raise ControlledDerivationError("end operand must be numeric")
    difference = end.value - start.value
    if difference < 0:
        raise ControlledDerivationError("end operand precedes start operand")
    return {
        "operation": operation,
        "start": {
            "label": start.label,
            "value": start.value,
            "evidence_indexes": list(start.evidence_indexes),
        },
        "end": {
            "label": end.label,
            "value": end.value,
            "evidence_indexes": list(end.evidence_indexes),
        },
        "difference": difference,
        "unit": unit,
        "deterministic": True,
    }


def deterministic_order(
    operands: Iterable[DerivedOperand],
) -> dict[str, Any]:
    """Order reviewed dated/numbered facts while preserving equal-value order."""

    items = list(operands)
    if not items:
        raise ControlledDerivationError("at least one operand is required")
    if any(not item.evidence_indexes for item in items):
        raise ControlledDerivationError("every operand requires evidence")
    if any(
        not isinstance(item.value, Real) or isinstance(item.value, bool)
        for item in items
    ):
        raise ControlledDerivationError("all operands must be numeric")
    ordered = sorted(enumerate(items), key=lambda pair: (pair[1].value, pair[0]))
    return {
        "operation": "chronological_order",
        "items": [
            {
                "label": item.label,
                "value": item.value,
                "evidence_indexes": list(item.evidence_indexes),
            }
            for _, item in ordered
        ],
        "deterministic": True,
    }
