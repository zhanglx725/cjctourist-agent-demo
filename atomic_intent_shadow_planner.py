"""Deterministic, audit-only P2-01 candidates for multiple read questions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_decision import validate_agent_decision
from atomic_read_plan import build_atomic_read_plan
from controlled_knowledge_query import identify_controlled_knowledge_plan
from single_fact_answer import identify_single_fact_kind
from tool_registry import RuntimePhase

_CONTROL_MARKERS = ("到", "继续", "下一站", "完成", "跳过", "结束", "重新规划", "重新安排", "路线")
_SPLITTER = ("，再", "。再", "；再", "，然后", "。然后")


@dataclass(frozen=True)
class AtomicShadowResult:
    decision_kind: str
    reason_codes: tuple[str, ...]
    candidates: tuple[dict[str, object], ...]

    def audit_dict(self) -> dict[str, object]:
        return {"decision_kind": self.decision_kind, "reason_codes": list(self.reason_codes), "candidates": [dict(item) for item in self.candidates], "planner_mode": "shadow"}


def _clarification(*reasons: str) -> AtomicShadowResult:
    return AtomicShadowResult("clarification", tuple(reasons), ())


def _parts(text: str) -> tuple[str, ...]:
    for separator in _SPLITTER:
        if separator in text:
            return tuple(part.strip(" ，。；") for part in text.split(separator) if part.strip(" ，。；"))
    return (text,)


def observe_atomic_read_intents(user_text: str, *, phase: RuntimePhase) -> AtomicShadowResult:
    """Produce only a bounded audit candidate; never executes a tool or action."""
    if not isinstance(user_text, str) or not user_text.strip():
        return _clarification("invalid_user_text")
    if any(marker in user_text for marker in _CONTROL_MARKERS):
        return _clarification("multiple_intents", "state_or_route_action")
    parts = _parts(user_text)
    if len(parts) < 2:
        return AtomicShadowResult("not_multi_intent", (), ())
    validations = []
    candidates: list[dict[str, object]] = []
    claims: dict[str, tuple[str, ...]] = {}
    for part in parts:
        if identify_single_fact_kind(part) is not None:
            intent, capability, evidence = "fact_question", "single_fact", ("reviewed_category", "registered_source")
        elif identify_controlled_knowledge_plan(part) is not None:
            intent, capability, evidence = "service_rule", "controlled_knowledge", ("closed_category", "registered_source")
        else:
            return _clarification("multiple_intents", "unresolved_read_capability")
        validation = validate_agent_decision({
            "intent": intent, "sub_intents": [], "requested_capability": capability,
            "target_text": part, "evidence_span": part, "confidence": 1.0,
            "requires_clarification": False, "requires_confirmation": False,
            "side_effect_level": "read_only",
        }, user_text=user_text)
        if not validation.accepted or validation.decision is None:
            return _clarification(validation.rejection_code or "candidate_rejected")
        validations.append(validation)
        claims[capability] = evidence
        candidates.append({
            "intent": intent, "sub_intents": [], "requested_capability": capability,
            "evidence_span": part, "confidence": 1.0, "requires_confirmation": False,
            "side_effect_level": "read_only", "context_scope": "user_text_only",
        })
    plan = build_atomic_read_plan(validations, phase=phase, evidence_claims=claims)
    if not plan.accepted:
        return _clarification(plan.reason or "atomic_plan_rejected")
    return AtomicShadowResult("atomic_read_plan", (), tuple(candidates))
