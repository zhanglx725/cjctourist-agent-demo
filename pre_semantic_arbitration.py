"""Read-only gate that protects deterministic flows from semantic models.

The gate does not choose a node ID, derive a route, or execute an action.  It
only answers whether the current turn has already been consumed by a frozen
deterministic or specialist capability, so semantic normalization must not
make a model request first.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from craft_knowledge import parse_craft_explanation_request, parse_craft_location_request
from term_card_runtime import is_explicit_term_question
from photo_spot_runtime import is_explicit_photo_request, is_unsafe_photo_request
from qa_context import is_qa_follow_up_detail_request, is_qa_subject_follow_up_request
from research_card_retrieval import is_explicit_research_question
from comparison_retrieval import is_explicit_comparison_question
from extended_profile_control import parse_extended_profile_control
from profile_update import is_profile_update_request
from single_fact_answer import identify_single_fact_kind
from tour_intent import classify_tour_intent
from tour_qa import is_point_inventory_request, resolve_ornament_story_scope_request
from visit_safety_rules import is_visit_safety_question


@dataclass(frozen=True)
class PreSemanticAction:
    """A non-executing explanation of why a model call is unnecessary."""

    consumed: bool
    reason: str | None = None
    route_target: str | None = None
    normalized_text: str | None = None
    model_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pending_action_reason(state: dict[str, Any]) -> PreSemanticAction | None:
    """Recognize only already-created pending actions; never create one."""
    interaction = state.get("tour_interaction_state") or {}
    pending_kind = interaction.get("pending_action_kind")
    if (
        state.get("pending_replan_time_confirmation")
        or state.get("pending_replan_proposal")
        or pending_kind in {"replan_time_confirmation", "replan_route_confirmation"}
    ):
        return PreSemanticAction(
            True,
            reason="pending_replan_confirmation",
            route_target="pending_action_resolver",
            model_required=False,
        )
    if state.get("pending_ornament_clarification"):
        return PreSemanticAction(
            True,
            reason="pending_specialist_clarification",
            route_target="tour_qa",
            model_required=False,
        )
    return None


def resolve_pre_semantic_action(
    state: dict[str, Any], user_text: str,
) -> PreSemanticAction:
    """Return whether a frozen path already owns this raw visitor turn.

    The caller must still route and validate through the existing event,
    profile, knowledge, or presentation code.  This function intentionally
    does not return executable arguments.
    """
    pending = _pending_action_reason(state)
    if pending is not None:
        return pending

    decision = classify_tour_intent(
        user_text, state.get("tour_state"), state.get("tour_interaction_state")
    )
    if decision.route_kind in {"tour_event", "route_request", "replan_request", "clarification"}:
        return PreSemanticAction(
            True,
            reason="deterministic_event_or_control",
            route_target=(
                "tour_event" if decision.route_kind == "tour_event" else decision.route_kind
            ),
            model_required=False,
        )

    if is_unsafe_photo_request(user_text) or is_visit_safety_question(user_text):
        return PreSemanticAction(
            True, reason="safety_rule", route_target="tour_qa", model_required=False
        )

    if (
        parse_craft_explanation_request(user_text) is not None
        or parse_craft_location_request(user_text) is not None
        or is_explicit_photo_request(user_text)
        or is_explicit_comparison_question(user_text)
        or is_explicit_research_question(user_text)
        or is_explicit_term_question(user_text)
        or resolve_ornament_story_scope_request(user_text, state.get("tour_state"))
        is not None
        or is_point_inventory_request(user_text, state.get("tour_state"))
        or is_qa_follow_up_detail_request(user_text)
        or is_qa_subject_follow_up_request(user_text)
    ):
        return PreSemanticAction(
            True, reason="specialist_channel", route_target="tour_qa", model_required=False
        )

    if identify_single_fact_kind(user_text) is not None:
        return PreSemanticAction(
            True, reason="deterministic_fact", route_target="reviewed_fact", model_required=False
        )
    # Profile controls are already interpreted by deterministic parsers.  They
    # may update only the approved VisitorProfile fields in their existing
    # node, so a semantic candidate must not race them for ownership.
    extended_control = parse_extended_profile_control(user_text)
    if extended_control.kind != "none" or is_profile_update_request(user_text):
        return PreSemanticAction(
            True,
            reason="deterministic_profile_control",
            route_target="profile_control",
            model_required=False,
        )
    return PreSemanticAction(False)
