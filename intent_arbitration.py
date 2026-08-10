"""Pure Workflow arbitration for semantic intent proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from semantic_intent_contract import (
    REQUIRED_ARGUMENT_KEYS,
    IntentCandidate,
    SemanticIntentEnvelope,
)


READ_ONLY_THRESHOLD = 0.80
STATE_MUTATION_THRESHOLD = 0.90

INTENT_ROUTE_TARGETS = {
    "select_language": "visitor_onboarding",
    "select_journey_mode": "journey_mode_selection",
    "provide_profile_preference": "profile_collection",
    "request_route": "profile_collection",
    "arrive_at_stop": "tour_event",
    "confirm_stop_complete": "tour_event",
    "confirm_stop_complete_and_next": "tour_event",
    "skip_stop": "tour_event",
    "request_next_stop": "tour_event",
    "request_stop_detail": "tour_event",
    "finish_tour": "tour_event",
    "request_replan": "prepare_replan",
    "confirm_replan": "confirm_replan",
    "confirm_replan_and_next": "confirm_replan_and_next",
    "cancel_replan": "cancel_replan",
    "ask_venue_question": "tour_qa",
    "ask_follow_up_detail": "qa_follow_up_detail",
    "update_profile": "profile_update",
    "request_summary": "visit_summary",
    "request_title_blessing": "post_visit_title_blessing",
}


@dataclass(frozen=True)
class ArbitrationResult:
    status: Literal["accepted", "clarification", "rejected"]
    route_target: str
    intent: str | None
    confidence: float | None
    arguments: dict[str, object]
    reason_code: str
    state_write_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "route_target": self.route_target,
            "intent": self.intent,
            "confidence": self.confidence,
            "arguments": dict(self.arguments),
            "reason_code": self.reason_code,
            "state_write_allowed": self.state_write_allowed,
        }


def _result(
    status: Literal["accepted", "clarification", "rejected"],
    route_target: str,
    *,
    candidate: IntentCandidate | None = None,
    reason_code: str,
    state_write_allowed: bool = False,
) -> ArbitrationResult:
    return ArbitrationResult(
        status=status, route_target=route_target,
        intent=candidate.intent if candidate else None,
        confidence=candidate.confidence if candidate else None,
        arguments=dict(candidate.arguments) if candidate else {},
        reason_code=reason_code, state_write_allowed=state_write_allowed,
    )


def arbitrate_intents(
    envelope: SemanticIntentEnvelope,
    state: Mapping[str, Any],
    *,
    deterministic_route_target: str | None = None,
) -> ArbitrationResult:
    """Choose one capability without performing any state mutation.

    A reviewed deterministic route is authoritative. Semantic candidates are
    considered only when no such route has already consumed the turn.
    """
    if deterministic_route_target:
        return _result(
            "accepted", deterministic_route_target,
            reason_code="deterministic_priority", state_write_allowed=False,
        )
    candidates = tuple(
        candidate for candidate in envelope.candidates
        if candidate.intent != "unknown" and candidate.intent in INTENT_ROUTE_TARGETS
    )
    if not candidates:
        return _result("rejected", "llm_think", reason_code="no_valid_candidate")
    mutating = tuple(candidate for candidate in candidates if candidate.state_mutating)
    if len(mutating) > 1:
        return _result("clarification", "clarification", reason_code="conflicting_state_intents")
    candidate = candidates[0]
    threshold = STATE_MUTATION_THRESHOLD if candidate.state_mutating else READ_ONLY_THRESHOLD
    if candidate.confidence < threshold:
        return _result(
            "clarification", "clarification", candidate=candidate,
            reason_code="confidence_below_execution_threshold",
        )
    if candidate.requires_confirmation:
        return _result(
            "clarification", "clarification", candidate=candidate,
            reason_code="explicit_confirmation_required",
        )
    if any(
        candidate.arguments.get(key) is None or candidate.arguments.get(key) == ""
        for key in REQUIRED_ARGUMENT_KEYS.get(candidate.intent, frozenset())
    ):
        return _result(
            "clarification", "clarification", candidate=candidate,
            reason_code="incomplete_arguments",
        )
    route_status = (state.get("tour_state") or {}).get("route_status")
    if candidate.intent in {
        "arrive_at_stop", "confirm_stop_complete", "confirm_stop_complete_and_next",
        "skip_stop", "request_next_stop", "request_stop_detail", "finish_tour",
    } and route_status != "touring":
        return _result(
            "rejected", "clarification", candidate=candidate,
            reason_code="intent_not_allowed_without_active_tour",
        )
    if candidate.intent in {"confirm_replan", "confirm_replan_and_next", "cancel_replan"} and not (
        state.get("pending_replan_proposal") or state.get("pending_replan_time_confirmation")
    ):
        return _result(
            "rejected", "clarification", candidate=candidate,
            reason_code="no_pending_replan",
        )
    return _result(
        "accepted", INTENT_ROUTE_TARGETS[candidate.intent], candidate=candidate,
        reason_code="semantic_candidate_authorized",
        state_write_allowed=candidate.state_mutating,
    )
