"""CA-08 all-or-nothing plans for multiple read-only questions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping

from agent_decision import DecisionValidation
from policy_gate import GateVerdict, evaluate_policy
from tool_registry import RuntimePhase


@dataclass(frozen=True)
class AtomicReadPlan:
    steps: tuple[GateVerdict, ...]
    resume_snapshot: dict[str, object] | None


@dataclass(frozen=True)
class AtomicPlanResult:
    accepted: bool
    plan: AtomicReadPlan | None
    reason: str | None


def build_atomic_read_plan(
    validations: Iterable[DecisionValidation], *, phase: RuntimePhase,
    evidence_claims: Mapping[str, Iterable[str]], resume_snapshot: Mapping[str, object] | None = None,
) -> AtomicPlanResult:
    """Approve all ordered read-only steps or return no plan at all."""
    values = tuple(validations)
    if not values or len(values) > 4:
        return AtomicPlanResult(False, None, "step_count_rejected")
    capabilities: set[str] = set()
    verdicts: list[GateVerdict] = []
    for validation in values:
        if not validation.accepted or validation.decision is None:
            return AtomicPlanResult(False, None, validation.rejection_code or "candidate_rejected")
        capability = validation.decision.requested_capability.value
        if capability in capabilities:
            return AtomicPlanResult(False, None, "duplicate_capability")
        capabilities.add(capability)
        verdict = evaluate_policy(validation, phase=phase, evidence_claims=evidence_claims.get(capability, ()))
        if not verdict.approved:
            return AtomicPlanResult(False, None, verdict.reason)
        verdicts.append(verdict)
    snapshot = dict(resume_snapshot) if resume_snapshot is not None else None
    return AtomicPlanResult(True, AtomicReadPlan(tuple(verdicts), snapshot), None)
