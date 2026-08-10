"""Closed, non-executing candidate protocol for controlled agent decisions.

CA-01 deliberately validates only a model-proposed *candidate*.  It knows no
graph routing, tools, state, or reviewed IDs.  A later deterministic resolver
may map an accepted candidate to reviewed entities; this module never accepts
such identifiers from model output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import uuid
from typing import Any, Mapping


class Intent(StrEnum):
    TOUR_CONTROL = "tour_control"
    ROUTE_PLANNING = "route_planning"
    REPLANNING = "replanning"
    TOUR_MODE_SELECTION = "tour_mode_selection"
    NARRATION_STYLE_SELECTION = "narration_style_selection"
    LOCALE_SELECTION = "locale_selection"
    RESUME_TOUR_FLOW = "resume_tour_flow"
    TERM_QUESTION = "term_question"
    ORNAMENT_QUESTION = "ornament_question"
    STOP_INVENTORY = "stop_inventory"
    CRAFT_LOCATION = "craft_location"
    FACT_QUESTION = "fact_question"
    SERVICE_RULE = "service_rule"
    RESEARCH = "research"
    ACADEMIC_ADVISOR = "academic_advisor"
    COMPARISON = "comparison"
    PHOTO = "photo"
    SAFETY = "safety"
    CLARIFICATION = "clarification"
    SMALL_TALK = "small_talk"


class Capability(StrEnum):
    TOUR_EVENT = "tour_event"
    ROUTE_PROPOSAL = "route_proposal"
    REPLAN_PROPOSAL = "replan_proposal"
    TOUR_MODE = "tour_mode"
    NARRATION_STYLE = "narration_style"
    LOCALE = "locale"
    RESUME_TOUR = "resume_tour"
    TERM = "term"
    ORNAMENT_DETAIL = "ornament_detail"
    POINT_INVENTORY = "point_inventory"
    CRAFT_LOCATION = "craft_location"
    SINGLE_FACT = "single_fact"
    VISIT_SERVICE = "visit_service"
    CONTROLLED_KNOWLEDGE = "controlled_knowledge"
    RESEARCH = "research"
    ACADEMIC_ADVISOR = "academic_advisor"
    COMPARISON = "comparison"
    PHOTO = "photo"
    SAFETY = "safety"
    CLARIFICATION = "clarification"
    SMALL_TALK = "small_talk"


class SideEffectLevel(StrEnum):
    READ_ONLY = "read_only"
    PROPOSAL = "proposal"
    CONFIRMED_STATE_CHANGE = "confirmed_state_change"
    PROHIBITED = "prohibited"


MIN_CONFIDENCE = 0.80
_REQUIRED_KEYS = frozenset({
    "intent", "sub_intents", "requested_capability", "target_text",
    "evidence_span", "confidence", "requires_clarification",
    "requires_confirmation", "side_effect_level",
})
_CAPABILITIES_BY_INTENT: dict[Intent, frozenset[Capability]] = {
    Intent.TOUR_CONTROL: frozenset({Capability.TOUR_EVENT}),
    Intent.ROUTE_PLANNING: frozenset({Capability.ROUTE_PROPOSAL}),
    Intent.REPLANNING: frozenset({Capability.REPLAN_PROPOSAL}),
    Intent.TOUR_MODE_SELECTION: frozenset({Capability.TOUR_MODE}),
    Intent.NARRATION_STYLE_SELECTION: frozenset({Capability.NARRATION_STYLE}),
    Intent.LOCALE_SELECTION: frozenset({Capability.LOCALE}),
    Intent.RESUME_TOUR_FLOW: frozenset({Capability.RESUME_TOUR}),
    Intent.TERM_QUESTION: frozenset({Capability.TERM}),
    Intent.ORNAMENT_QUESTION: frozenset({Capability.ORNAMENT_DETAIL}),
    Intent.STOP_INVENTORY: frozenset({Capability.POINT_INVENTORY}),
    Intent.CRAFT_LOCATION: frozenset({Capability.CRAFT_LOCATION}),
    Intent.FACT_QUESTION: frozenset({Capability.SINGLE_FACT}),
    Intent.SERVICE_RULE: frozenset({Capability.VISIT_SERVICE, Capability.CONTROLLED_KNOWLEDGE}),
    Intent.RESEARCH: frozenset({Capability.RESEARCH}),
    Intent.ACADEMIC_ADVISOR: frozenset({Capability.ACADEMIC_ADVISOR}),
    Intent.COMPARISON: frozenset({Capability.COMPARISON}),
    Intent.PHOTO: frozenset({Capability.PHOTO}),
    Intent.SAFETY: frozenset({Capability.SAFETY}),
    Intent.CLARIFICATION: frozenset({Capability.CLARIFICATION}),
    Intent.SMALL_TALK: frozenset({Capability.SMALL_TALK}),
}
_NEGATION_OR_HYPOTHESIS_MARKERS = ("不要", "别", "不想", "如果", "假如", "要是", "能不能")


@dataclass(frozen=True)
class AgentDecision:
    """An accepted candidate. ``decision_id`` is generated locally, never parsed."""

    decision_id: str
    intent: Intent
    sub_intents: tuple[Intent, ...]
    requested_capability: Capability
    target_text: str
    evidence_span: str
    confidence: float
    requires_clarification: bool
    requires_confirmation: bool
    side_effect_level: SideEffectLevel

    def audit_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "intent": self.intent.value,
            "sub_intents": [item.value for item in self.sub_intents],
            "requested_capability": self.requested_capability.value,
            "target_text": self.target_text,
            "evidence_span": self.evidence_span,
            "confidence": self.confidence,
            "requires_clarification": self.requires_clarification,
            "requires_confirmation": self.requires_confirmation,
            "side_effect_level": self.side_effect_level.value,
        }


@dataclass(frozen=True)
class DecisionValidation:
    accepted: bool
    decision: AgentDecision | None
    rejection_code: str | None = None
    clarification_required: bool = False


def _reject(code: str, *, clarification_required: bool = False) -> DecisionValidation:
    return DecisionValidation(False, None, code, clarification_required)


def _enum(enum_type: type[StrEnum], value: object) -> StrEnum | None:
    if not isinstance(value, str):
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _load_candidate(candidate: str | Mapping[str, Any]) -> Mapping[str, Any] | None:
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            return None
    return candidate if isinstance(candidate, Mapping) else None


def validate_agent_decision(
    candidate: str | Mapping[str, Any],
    *,
    user_text: str,
) -> DecisionValidation:
    """Accept only an exact closed-schema candidate; never execute it."""
    payload = _load_candidate(candidate)
    if payload is None:
        return _reject("invalid_json")
    if set(payload) != _REQUIRED_KEYS:
        return _reject("schema_keys_rejected")
    if not isinstance(user_text, str) or not user_text:
        return _reject("invalid_user_text")

    intent = _enum(Intent, payload["intent"])
    capability = _enum(Capability, payload["requested_capability"])
    side_effect = _enum(SideEffectLevel, payload["side_effect_level"])
    if intent is None or capability is None or side_effect is None:
        return _reject("enum_rejected")
    if capability not in _CAPABILITIES_BY_INTENT[intent]:
        return _reject("intent_capability_mismatch")

    sub_intents_raw = payload["sub_intents"]
    if not isinstance(sub_intents_raw, list) or len(sub_intents_raw) > 4:
        return _reject("sub_intents_rejected")
    sub_intents = tuple(_enum(Intent, value) for value in sub_intents_raw)
    if any(value is None for value in sub_intents) or intent in sub_intents or len(set(sub_intents)) != len(sub_intents):
        return _reject("sub_intents_rejected")

    target_text, evidence_span = payload["target_text"], payload["evidence_span"]
    if (
        not isinstance(target_text, str) or not isinstance(evidence_span, str)
        or not target_text or not evidence_span
        or target_text not in user_text or evidence_span not in user_text
    ):
        return _reject("span_not_in_user_text", clarification_required=True)
    if target_text != evidence_span:
        return _reject("span_mismatch", clarification_required=True)

    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        return _reject("confidence_rejected")
    if confidence < MIN_CONFIDENCE:
        return _reject("low_confidence", clarification_required=True)
    if not isinstance(payload["requires_clarification"], bool) or not isinstance(payload["requires_confirmation"], bool):
        return _reject("boolean_rejected")
    if payload["requires_clarification"] and intent is not Intent.CLARIFICATION:
        return _reject("clarification_combination_rejected")
    if intent is Intent.CLARIFICATION and not payload["requires_clarification"]:
        return _reject("clarification_combination_rejected")
    if side_effect is SideEffectLevel.CONFIRMED_STATE_CHANGE and not payload["requires_confirmation"]:
        return _reject("confirmation_required")
    if side_effect in {SideEffectLevel.PROPOSAL, SideEffectLevel.CONFIRMED_STATE_CHANGE} and intent in {Intent.SAFETY, Intent.CLARIFICATION, Intent.SMALL_TALK}:
        return _reject("side_effect_combination_rejected")
    if side_effect is not SideEffectLevel.READ_ONLY and any(marker in target_text for marker in _NEGATION_OR_HYPOTHESIS_MARKERS):
        return _reject("ambiguous_control_language", clarification_required=True)

    return DecisionValidation(
        True,
        AgentDecision(
            decision_id=f"dec_{uuid.uuid4().hex}", intent=intent, sub_intents=tuple(sub_intents),
            requested_capability=capability, target_text=target_text, evidence_span=evidence_span,
            confidence=float(confidence), requires_clarification=payload["requires_clarification"],
            requires_confirmation=payload["requires_confirmation"], side_effect_level=side_effect,
        ),
    )
