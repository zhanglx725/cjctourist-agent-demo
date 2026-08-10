"""Schema and fail-closed validation for semantic intent proposals.

The contract deliberately contains business intents, never LangGraph node names.
It is safe to persist for audit, but it is not an execution instruction and has
no authority to mutate route, profile, TourState, or NarrationCoverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "semantic_intent_envelope_v1"
MAX_CANDIDATES = 3

INTENT_ARGUMENT_KEYS: dict[str, frozenset[str]] = {
    "select_language": frozenset({"language"}),
    "select_journey_mode": frozenset({"journey_mode"}),
    "provide_profile_preference": frozenset({"field", "value"}),
    "request_route": frozenset({"available_minutes", "minimize_walking"}),
    "arrive_at_stop": frozenset({"location_text"}),
    "confirm_stop_complete": frozenset(),
    "confirm_stop_complete_and_next": frozenset(),
    "skip_stop": frozenset({"stop_text"}),
    "request_next_stop": frozenset(),
    "request_stop_detail": frozenset({"stop_text"}),
    "finish_tour": frozenset(),
    "request_replan": frozenset({"remaining_minutes", "origin_text"}),
    "confirm_replan": frozenset(),
    "confirm_replan_and_next": frozenset(),
    "cancel_replan": frozenset(),
    "ask_venue_question": frozenset({"subject_text", "detail_level"}),
    "ask_follow_up_detail": frozenset({"subject_text"}),
    "update_profile": frozenset({"field", "value"}),
    "request_summary": frozenset(),
    "request_title_blessing": frozenset(),
    "unknown": frozenset(),
}
INTENT_WHITELIST = frozenset(INTENT_ARGUMENT_KEYS)

REQUIRED_ARGUMENT_KEYS: dict[str, frozenset[str]] = {
    "select_language": frozenset({"language"}),
    "select_journey_mode": frozenset({"journey_mode"}),
    "provide_profile_preference": frozenset({"field", "value"}),
    "arrive_at_stop": frozenset({"location_text"}),
    "request_replan": frozenset({"remaining_minutes"}),
    "ask_venue_question": frozenset({"subject_text", "detail_level"}),
    "update_profile": frozenset({"field", "value"}),
}

STATE_MUTATING_INTENTS = frozenset(
    {
        "select_language",
        "select_journey_mode",
        "provide_profile_preference",
        "request_route",
        "arrive_at_stop",
        "confirm_stop_complete",
        "confirm_stop_complete_and_next",
        "skip_stop",
        "finish_tour",
        "request_replan",
        "confirm_replan",
        "confirm_replan_and_next",
        "cancel_replan",
        "update_profile",
    }
)


@dataclass(frozen=True)
class IntentCandidate:
    intent: str
    confidence: float
    target: str | None = None
    arguments: dict[str, object] = field(default_factory=dict)
    source: str = "model"
    requires_confirmation: bool = False
    evidence_span: str = ""

    @property
    def state_mutating(self) -> bool:
        return self.intent in STATE_MUTATING_INTENTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "target": self.target,
            "arguments": dict(self.arguments),
            "source": self.source,
            "requires_confirmation": self.requires_confirmation,
            "evidence_span": self.evidence_span,
        }


@dataclass(frozen=True)
class SemanticIntentEnvelope:
    candidates: tuple[IntentCandidate, ...] = ()
    ambiguity_reason: str | None = None
    raw_text_preserved: bool = True
    model_called: bool = False
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "ambiguity_reason": self.ambiguity_reason,
            "raw_text_preserved": self.raw_text_preserved,
            "model_called": self.model_called,
        }


def _valid_argument_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return not isinstance(value, float) or value == value
    if isinstance(value, list):
        return len(value) <= 20 and all(_valid_argument_value(item) for item in value)
    return False


def validate_intent_candidate(
    raw_text: str,
    value: Mapping[str, Any],
) -> IntentCandidate | None:
    """Validate one proposal without resolving targets or executing actions."""
    required = {
        "intent", "confidence", "target", "arguments", "source",
        "requires_confirmation", "evidence_span",
    }
    if set(value) != required:
        return None
    intent = value.get("intent")
    confidence = value.get("confidence")
    target = value.get("target")
    arguments = value.get("arguments")
    source = value.get("source")
    requires_confirmation = value.get("requires_confirmation")
    evidence_span = value.get("evidence_span")
    if intent not in INTENT_WHITELIST:
        return None
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        return None
    if target is not None and (
        not isinstance(target, str)
        or not target.strip()
        or target not in raw_text
    ):
        return None
    if not isinstance(arguments, dict):
        return None
    if not set(arguments).issubset(INTENT_ARGUMENT_KEYS[str(intent)]):
        return None
    if not REQUIRED_ARGUMENT_KEYS.get(str(intent), frozenset()).issubset(arguments):
        return None
    if not all(isinstance(key, str) and _valid_argument_value(item) for key, item in arguments.items()):
        return None
    if source not in {"deterministic", "model", "legacy_adapter"}:
        return None
    if not isinstance(requires_confirmation, bool):
        return None
    if not isinstance(evidence_span, str):
        return None
    if evidence_span and evidence_span not in raw_text:
        return None
    if intent != "unknown" and not evidence_span:
        return None
    return IntentCandidate(
        intent=str(intent), confidence=float(confidence), target=target,
        arguments=dict(arguments), source=str(source),
        requires_confirmation=requires_confirmation, evidence_span=evidence_span,
    )


def build_intent_envelope(
    raw_text: str,
    values: Iterable[Mapping[str, Any]],
    *,
    ambiguity_reason: str | None = None,
    model_called: bool = False,
) -> SemanticIntentEnvelope:
    """Return at most three unique, confidence-ordered validated candidates."""
    validated: list[IntentCandidate] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        candidate = validate_intent_candidate(raw_text, value)
        if candidate is None:
            continue
        identity = (candidate.intent, candidate.target)
        if identity in seen:
            continue
        seen.add(identity)
        validated.append(candidate)
    validated.sort(key=lambda candidate: candidate.confidence, reverse=True)
    return SemanticIntentEnvelope(
        candidates=tuple(validated[:MAX_CANDIDATES]),
        ambiguity_reason=ambiguity_reason,
        model_called=model_called,
    )
