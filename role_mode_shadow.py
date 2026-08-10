"""Deterministic, read-only role-mode selection for narration Shadow.

This module is deliberately narrower than the semantic router. It recognizes
only the approved narration-style catalog and returns an audit record. It
never edits ``VisitorProfile`` and never produces route, fact, evidence, or
visitor-message data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from narration_style_policy import approved_style_ids
from profile_dialogue import EXPLICIT_STYLE_PHRASES, STYLE_ALIASES


ROLE_MODE_SCHEMA_VERSION = "role_mode_shadow_v1"
_ROLE_MODE_ORDER = approved_style_ids()
ROLE_MODE_IDS = frozenset(_ROLE_MODE_ORDER)
ROLE_MODE_SURFACES = (
    "route_planning_shadow", "route_opening_shadow", "stop_guidance_shadow",
    "navigation_shadow", "tour_closing_shadow",
)

_NATURAL_ROLE_PHRASES = {
    # These phrases are reviewed intent surfaces, not inferred demographics.
    # They preserve the same bounded role IDs as explicit catalog selections.
    "ancient_scholar": ("古风一点", "古风讲解"),
    "child": (
        "适合孩子理解", "适合孩子", "适合小朋友理解", "适合小朋友",
        "给小朋友讲",
    ),
}

_EXPLICIT_ROLE_PHRASES = {
    style_id: tuple(dict.fromkeys((
        *STYLE_ALIASES.get(style_id, ()),
        *EXPLICIT_STYLE_PHRASES.get(style_id, ()),
        *_NATURAL_ROLE_PHRASES.get(style_id, ()),
    )))
    # Preserve the reviewed catalog order so a conflict has deterministic
    # candidate ordering across processes and Python hash seeds.
    for style_id in _ROLE_MODE_ORDER
}

# These are intentionally not treated as aliases for a supported role.  A
# request for an unreviewed persona must remain a clarification, not silently
# fall back to one of the three reviewed roles.
_UNSUPPORTED_ROLE_MARKERS = (
    "抽象讲解", "脱口秀模式", "诗人模式", "戏剧模式",
    "情绪陪伴模式", "机器人模式",
)

_PRESENTATION_STRATEGIES = {
    "ancient_scholar": {
        "organization": "preserve_approved_fact_order",
        "sentence_strategy": "restrained_classical_connectors",
        "interaction": "preserve_legacy_interaction_policy",
        "fact_boundary": "approved_facts_only",
    },
    "child": {
        "organization": "one_idea_per_short_sentence",
        "sentence_strategy": "concrete_observation_and_simple_terms",
        "interaction": "low_pressure_observation_only",
        "fact_boundary": "approved_facts_and_safety_unchanged",
    },
    "listen_only": {
        "organization": "continuous_fact_ordered_narration",
        "sentence_strategy": "calm_compact_sentences",
        "interaction": "no_proactive_questions_or_tasks",
        "fact_boundary": "approved_facts_and_required_safety_only",
    },
}

_DEFAULT_PRESENTATION_STRATEGY = {
    "organization": "preserve_approved_fact_order",
    "sentence_strategy": "reviewed_style_brief_only",
    "interaction": "preserve_reviewed_interaction_policy",
    "fact_boundary": "approved_facts_and_safety_unchanged",
}


@dataclass(frozen=True)
class RoleModeShadowResolution:
    """The bounded role-selection audit kept in the thread checkpoint."""

    status: str
    selected_style_id: str | None
    candidate_style_ids: tuple[str, ...]
    confidence: float
    source: str
    applicability: dict[str, Any]
    presentation_strategy: dict[str, Any]
    reason_codes: tuple[str, ...] = ()
    state_writes: tuple[str, ...] = ()
    legacy_preserved: bool = True
    schema_version: str = ROLE_MODE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "selected_style_id": self.selected_style_id,
            "candidate_style_ids": list(self.candidate_style_ids),
            "confidence": self.confidence,
            "source": self.source,
            "applicability": dict(self.applicability),
            "presentation_strategy": dict(self.presentation_strategy),
            "reason_codes": list(self.reason_codes),
            "state_writes": list(self.state_writes),
            "legacy_preserved": self.legacy_preserved,
        }


def _not_requested(reason: str = "no_role_request") -> RoleModeShadowResolution:
    return RoleModeShadowResolution(
        status="not_requested",
        selected_style_id=None,
        candidate_style_ids=(),
        confidence=0.0,
        source="none",
        applicability={"surfaces": list(ROLE_MODE_SURFACES)},
        presentation_strategy={},
        reason_codes=(reason,),
    )


def _clarification(reason: str, candidates: tuple[str, ...] = ()) -> RoleModeShadowResolution:
    return RoleModeShadowResolution(
        status="clarification",
        selected_style_id=None,
        candidate_style_ids=candidates,
        confidence=0.0,
        source="conflict",
        applicability={
            "surfaces": list(ROLE_MODE_SURFACES),
            "requires_user_choice": True,
        },
        presentation_strategy={},
        reason_codes=(reason,),
    )


def _selected(style_id: str, *, source: str, confidence: float) -> RoleModeShadowResolution:
    return RoleModeShadowResolution(
        status="selected",
        selected_style_id=style_id,
        candidate_style_ids=(style_id,),
        confidence=confidence,
        source=source,
        applicability={
            "surfaces": list(ROLE_MODE_SURFACES),
            "facts": "approved_plan_only",
            "state_mutation": False,
        },
        presentation_strategy=dict(
            _PRESENTATION_STRATEGIES.get(style_id, _DEFAULT_PRESENTATION_STRATEGY)
        ),
    )


def _explicit_matches(text: str) -> tuple[str, ...]:
    return tuple(
        style_id
        for style_id, phrases in _EXPLICIT_ROLE_PHRASES.items()
        if any(phrase in text for phrase in phrases)
    )


def _profile_matches(profile: Mapping[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(profile, Mapping):
        return ()
    matches: list[str] = []
    explanation_style = profile.get("explanation_style")
    if isinstance(explanation_style, str) and explanation_style in ROLE_MODE_IDS:
        matches.append(explanation_style)
    if profile.get("audience_mode") == "child_friendly":
        matches.append("child")
    if profile.get("interaction_mode") == "listen_only":
        matches.append("listen_only")
    return tuple(dict.fromkeys(matches))


def resolve_role_mode(
    user_text: str,
    visitor_profile: Mapping[str, Any] | None = None,
    prior_resolution: Mapping[str, Any] | None = None,
) -> RoleModeShadowResolution:
    """Resolve one reviewed role without inferring personal attributes.

    Explicit requests win over an existing profile only when they identify
    exactly one role.  Multiple explicit roles, multiple conflicting profile
    roles, and unsupported personas all fail closed into a clarification
    record.  A prior explicit selection may be carried across turns as an
    audit-only context; it is never copied into the visitor profile.
    """

    text = str(user_text or "")
    explicit = _explicit_matches(text)
    if any(marker in text for marker in _UNSUPPORTED_ROLE_MARKERS):
        return _clarification("unsupported_role_request")
    if len(explicit) > 1:
        return _clarification("conflicting_role_request", explicit)
    if len(explicit) == 1:
        return _selected(explicit[0], source="explicit_request", confidence=1.0)

    profile_matches = _profile_matches(visitor_profile)
    if len(profile_matches) > 1:
        return _clarification("conflicting_profile_role", profile_matches)
    if len(profile_matches) == 1:
        return _selected(profile_matches[0], source="visitor_profile", confidence=0.95)

    if isinstance(prior_resolution, Mapping) and prior_resolution.get("status") == "selected":
        prior_style = prior_resolution.get("selected_style_id")
        if isinstance(prior_style, str) and prior_style in ROLE_MODE_IDS:
            return _selected(str(prior_style), source="inherited_shadow", confidence=0.9)
    return _not_requested()


__all__ = [
    "ROLE_MODE_IDS",
    "ROLE_MODE_SCHEMA_VERSION",
    "RoleModeShadowResolution",
    "resolve_role_mode",
]
