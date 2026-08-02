"""CA-06 deterministic preflight gate; it approves no execution itself."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent_decision import Capability, DecisionValidation, SideEffectLevel
from tool_registry import RegistrySideEffect, RuntimePhase, UnknownToolError, get_capability


_REGISTRY_CAPABILITY = {
    Capability.TERM: "term", Capability.ORNAMENT_DETAIL: "object",
    Capability.POINT_INVENTORY: "point_inventory", Capability.CRAFT_LOCATION: "craft",
    Capability.SINGLE_FACT: "single_fact", Capability.VISIT_SERVICE: "visit_service",
    Capability.RESEARCH: "research", Capability.COMPARISON: "comparison",
    Capability.PHOTO: "photo",
}


@dataclass(frozen=True)
class GateVerdict:
    approved: bool
    reason: str
    tool_name: str | None = None
    required_evidence: tuple[str, ...] = ()


def evaluate_policy(
    validation: DecisionValidation, *, phase: RuntimePhase,
    evidence_claims: Iterable[str] = (),
) -> GateVerdict:
    """Fail closed for any unregistered, unqualified, or non-read-only plan."""
    if not validation.accepted or validation.decision is None:
        return GateVerdict(False, validation.rejection_code or "candidate_rejected")
    decision = validation.decision
    if decision.requires_clarification:
        return GateVerdict(False, "clarification_required")
    if decision.requires_confirmation:
        return GateVerdict(False, "confirmation_required")
    if decision.side_effect_level is not SideEffectLevel.READ_ONLY:
        return GateVerdict(False, "side_effect_rejected")
    registry_capability = _REGISTRY_CAPABILITY.get(decision.requested_capability)
    if registry_capability is None:
        return GateVerdict(False, "capability_unregistered")
    try:
        spec = get_capability(registry_capability)
    except UnknownToolError:
        return GateVerdict(False, "capability_unregistered")
    if phase not in spec.allowed_phases:
        return GateVerdict(False, "phase_rejected")
    if spec.side_effect_level is not RegistrySideEffect.READ_ONLY or spec.requires_confirmation:
        return GateVerdict(False, "tool_policy_rejected")
    claims = frozenset(str(item) for item in evidence_claims)
    missing = tuple(item for item in spec.evidence_requirements if item not in claims)
    if missing:
        return GateVerdict(False, "evidence_missing", spec.tool_name, missing)
    return GateVerdict(True, "approved", spec.tool_name, spec.evidence_requirements)
