"""Executable contracts for visitor-visible response scenes.

This registry is deliberately data-only in its first P1 step.  It records the
public boundary that later routing and rendering changes must use, without
changing fact sources, state transitions, or existing message behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class PublicSceneKind(StrEnum):
    """The only scene kinds permitted for the P1 public narration layer."""

    ARRIVAL_CONFIRMATION = "arrival_confirmation"
    ROUTE_OPENING = "route_opening"
    STOP_GUIDANCE = "stop_guidance"
    NAVIGATION = "navigation"
    TOUR_QA = "tour_qa"
    SAFETY_REFUSAL = "safety_refusal"
    TOUR_CLOSING = "tour_closing"


@dataclass(frozen=True)
class PublicSceneContract:
    """Non-negotiable public boundary for one visitor response scene."""

    kind: PublicSceneKind
    allowed_inputs: frozenset[str]
    required_semantics: frozenset[str]
    prohibited_semantics: frozenset[str]
    role_style_allowed: bool
    llm_allowed: bool
    validator_name: str
    fallback_name: str


@dataclass(frozen=True)
class PublicSceneValidation:
    """Fail-closed validation result for a deterministic public scene."""

    accepted: bool
    reason_codes: tuple[str, ...] = ()


def _contract(
    kind: PublicSceneKind,
    *,
    inputs: tuple[str, ...],
    required: tuple[str, ...],
    prohibited: tuple[str, ...],
    role_style_allowed: bool,
    llm_allowed: bool,
    validator_name: str,
    fallback_name: str,
) -> PublicSceneContract:
    return PublicSceneContract(
        kind=kind,
        allowed_inputs=frozenset(inputs),
        required_semantics=frozenset(required),
        prohibited_semantics=frozenset(prohibited),
        role_style_allowed=role_style_allowed,
        llm_allowed=llm_allowed,
        validator_name=validator_name,
        fallback_name=fallback_name,
    )


PUBLIC_SCENE_CONTRACTS: Mapping[PublicSceneKind, PublicSceneContract] = MappingProxyType({
    PublicSceneKind.ARRIVAL_CONFIRMATION: _contract(
        PublicSceneKind.ARRIVAL_CONFIRMATION,
        inputs=("display_name", "selected_style_id"),
        required=("arrived_display_name", "begin_stop_guidance_now"),
        prohibited=("observation_action", "object_story", "craft_definition", "route_opening", "point_opening_phrase"),
        role_style_allowed=True,
        llm_allowed=False,
        validator_name="validate_arrival_confirmation",
        fallback_name="deterministic_arrival_confirmation",
    ),
    PublicSceneKind.ROUTE_OPENING: _contract(
        PublicSceneKind.ROUTE_OPENING,
        inputs=("route_plan", "route_theme", "first_stop", "selected_style_id", "route_opening_brief"),
        required=("venue_overview", "route_theme", "visit_method", "first_stop_handoff"),
        prohibited=("point_opening_phrase", "first_object_full_story", "replay_without_explicit_intent"),
        role_style_allowed=True,
        llm_allowed=True,
        validator_name="validate_route_opening",
        fallback_name="deterministic_route_opening",
    ),
    PublicSceneKind.STOP_GUIDANCE: _contract(
        PublicSceneKind.STOP_GUIDANCE,
        inputs=("approved_stop_facts", "stop_location", "stop_shape", "stop_story", "selected_style_id", "stop_guidance_brief"),
        required=("approved_fact_coverage", "on_site_observation", "natural_closing"),
        prohibited=("cross_stop_facts", "internal_evidence", "unapproved_fact"),
        role_style_allowed=True,
        llm_allowed=True,
        validator_name="validate_stop_guidance",
        fallback_name="deterministic_stop_guidance",
    ),
    PublicSceneKind.NAVIGATION: _contract(
        PublicSceneKind.NAVIGATION,
        inputs=("next_stop", "approved_direction", "walking_estimate", "on_site_reminder", "selected_style_id"),
        required=("next_stop", "direction_or_path"),
        prohibited=("current_stop_story", "next_stop_story", "point_opening_phrase", "route_overview", "changed_direction_or_distance"),
        role_style_allowed=True,
        llm_allowed=True,
        validator_name="validate_navigation",
        fallback_name="deterministic_navigation",
    ),
    PublicSceneKind.TOUR_QA: _contract(
        PublicSceneKind.TOUR_QA,
        inputs=("approved_public_answer", "fact_evidence", "dynamic_information_notice"),
        required=("direct_answer", "public_safety_boundary"),
        prohibited=("role_opening", "role_bridge", "role_closing", "point_guidance_phrase"),
        role_style_allowed=False,
        llm_allowed=False,
        validator_name="validate_tour_qa",
        fallback_name="approved_public_answer",
    ),
    PublicSceneKind.SAFETY_REFUSAL: _contract(
        PublicSceneKind.SAFETY_REFUSAL,
        inputs=("safety_decision", "safe_alternative"),
        required=("clear_direct_refusal_or_clarification", "safe_alternative"),
        prohibited=("role_play", "joke", "weakened_prohibition", "location_resolution", "photo_candidate_query", "rag_query"),
        role_style_allowed=False,
        llm_allowed=False,
        validator_name="validate_safety_refusal",
        fallback_name="deterministic_safety_refusal",
    ),
    PublicSceneKind.TOUR_CLOSING: _contract(
        PublicSceneKind.TOUR_CLOSING,
        inputs=("visit_summary", "selected_style_id"),
        required=("visit_completion"),
        prohibited=("new_unapproved_facts", "point_opening_phrase"),
        role_style_allowed=True,
        llm_allowed=True,
        validator_name="validate_tour_closing",
        fallback_name="deterministic_tour_closing",
    ),
})


def get_public_scene_contract(kind: PublicSceneKind | str) -> PublicSceneContract:
    """Return a known contract and fail closed for unknown public scenes."""
    try:
        scene_kind = PublicSceneKind(kind)
    except ValueError as exc:
        raise ValueError(f"unknown public scene kind: {kind!r}") from exc
    return PUBLIC_SCENE_CONTRACTS[scene_kind]


def public_scene_kinds() -> tuple[PublicSceneKind, ...]:
    """Return scene kinds in stable contract-registration order."""
    return tuple(PUBLIC_SCENE_CONTRACTS)


def render_arrival_confirmation(display_name: str) -> str:
    """Render the deterministic, one-sentence arrival public response.

    Arrival is intentionally not role-realized or model-generated: the
    contract permits a future reviewed tone adjustment, but it may never add
    point-body material to this acknowledgement.
    """
    contract = get_public_scene_contract(PublicSceneKind.ARRIVAL_CONFIRMATION)
    if contract.llm_allowed:
        raise ValueError("arrival confirmation must remain deterministic")
    name = " ".join(str(display_name or "").split())
    if not name:
        raise ValueError("arrival confirmation requires a display name")
    return f"你已到达{name}，现在开始本点讲解。"


def validate_navigation(message: str, *, deterministic_message: str) -> PublicSceneValidation:
    """Accept only the reviewed navigation payload for this transition.

    Navigation may not acquire a point-story or a generic guide opening while
    moving between stops.  Equality with the deterministic renderer is the
    narrowest boundary: stop name, direction, route and walk estimate remain
    exactly those derived from the reviewed spatial graph.
    """
    if not isinstance(deterministic_message, str) or not deterministic_message.strip():
        return PublicSceneValidation(False, ("navigation_fallback_unavailable",))
    if not isinstance(message, str) or message.strip() != deterministic_message.strip():
        return PublicSceneValidation(False, ("navigation_payload_changed",))
    return PublicSceneValidation(True)


_SAFETY_REFUSAL_MODES = frozenset({
    "photo_safety_refusal",
    "photo_safety_clarification",
    "photo_safety_restriction",
})


def validate_safety_refusal(
    message: str,
    *,
    deterministic_message: str,
    mode: str,
) -> PublicSceneValidation:
    """Accept only the safety decision that was made before QA and retrieval.

    The caller supplies the already-determined safety response; this validator
    never classifies safety itself and therefore cannot weaken a prohibition or
    turn it into role narration.
    """
    if mode not in _SAFETY_REFUSAL_MODES:
        return PublicSceneValidation(False, ("unsupported_safety_mode",))
    if not isinstance(deterministic_message, str) or not deterministic_message.strip():
        return PublicSceneValidation(False, ("safety_fallback_unavailable",))
    if not isinstance(message, str) or message.strip() != deterministic_message.strip():
        return PublicSceneValidation(False, ("safety_payload_changed",))
    return PublicSceneValidation(True)
