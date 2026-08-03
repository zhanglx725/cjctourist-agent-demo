"""Deterministic C6 mapping from VisitorProfile to guidance execution policy.

This module intentionally does not import Agent, TourState, RAG, StopProgram,
or any knowledge-card loader.  It is the single future-facing policy source;
C7 may consume it only after separately validating budget and evidence bounds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from visitor_profile import VisitorProfile, profile_from_dict


DETAIL_POLICY = {
    "short": {
        "max_items_per_stop": 1,
        "explanation_length": "short",
        "expansion_depth": "minimal",
        "comparison_enabled": False,
        "research_extension_enabled": False,
    },
    "standard": {
        "max_items_per_stop": 2,
        "explanation_length": "standard",
        "expansion_depth": "standard",
        "comparison_enabled": False,
        "research_extension_enabled": False,
    },
    "deep": {
        "max_items_per_stop": 3,
        "explanation_length": "detailed",
        "expansion_depth": "deep",
        "comparison_enabled": True,
        "research_extension_enabled": True,
    },
}

AUDIENCE_POLICY = {
    "standard": {"vocabulary_level": "general", "optional_deepening_enabled": False},
    "child_friendly": {"vocabulary_level": "simple", "optional_deepening_enabled": False},
    "family": {"vocabulary_level": "simple", "optional_deepening_enabled": False},
    "study": {"vocabulary_level": "general", "optional_deepening_enabled": True},
    "mixed_group": {"vocabulary_level": "simple", "optional_deepening_enabled": True},
}

STYLE_POLICY = {
    "standard": "standard",
    "story": "story",
    "technical": "technical",
    "interactive": "interactive",
    "expert": "expert",
}

KNOWLEDGE_POLICY = {
    "general": {"term_explanation_enabled": True, "citation_detail": "brief", "professional_supplement_enabled": False},
    "enthusiast": {"term_explanation_enabled": True, "citation_detail": "standard", "professional_supplement_enabled": True},
    "professional": {"term_explanation_enabled": True, "citation_detail": "detailed", "professional_supplement_enabled": True},
}

INTERACTION_POLICY = {
    "listen_only": {"interaction_task_enabled": False, "proactive_question_enabled": False},
    "normal": {"interaction_task_enabled": False, "proactive_question_enabled": False},
    "interactive_tasks": {"interaction_task_enabled": True, "proactive_question_enabled": True},
}


@dataclass(frozen=True)
class GuidancePolicy:
    """Auditable C6 output; all fields are preferences, never factual evidence."""

    audience_mode: str
    knowledge_level: str
    explanation_style: str
    interaction_mode: str
    max_items_per_stop: int
    explanation_length: str
    expansion_depth: str
    vocabulary_level: str
    narrative_mode: str
    interaction_task_enabled: bool
    proactive_question_enabled: bool
    comparison_enabled: bool
    research_extension_enabled: bool
    term_explanation_enabled: bool
    citation_detail: str
    optional_deepening_enabled: bool
    professional_supplement_enabled: bool
    fact_evidence_required: bool
    budget_cap_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validated_profile(profile: VisitorProfile | dict[str, Any]) -> VisitorProfile:
    if isinstance(profile, VisitorProfile):
        return profile
    if isinstance(profile, dict):
        # C5 remains the sole validation authority for dict input.
        return profile_from_dict(profile)
    raise TypeError("profile 必须是 VisitorProfile 或已序列化的画像字典。")


def build_guidance_policy(
    profile: VisitorProfile | dict[str, Any], *, detail_level_override: str | None = None
) -> GuidancePolicy:
    """Build a stable policy without mutating profile or planning any content.

    Conflict order is encoded here once: factual/safety limits remain outside
    C6 and always dominate; then listen_only disables interaction; then
    child/family/mixed audience boundaries select the main vocabulary; the
    knowledge level adjusts optional terminology/citation detail without
    changing the detail-level time/length limits.
    """
    value = _validated_profile(profile)
    effective_detail_level = detail_level_override or value.detail_level
    if effective_detail_level not in DETAIL_POLICY:
        raise ValueError("detail_level_override must be short, standard, deep, or None")
    detail = DETAIL_POLICY[effective_detail_level]
    audience = AUDIENCE_POLICY[value.audience_mode]
    knowledge = KNOWLEDGE_POLICY[value.knowledge_level]
    interaction = INTERACTION_POLICY[value.interaction_mode]

    # Child/family/mixed all retain a simple main explanation.  A professional
    # setting can offer a supplement but must not override that shared main
    # vocabulary.  In particular, professional does not imply deep.
    vocabulary_level = audience["vocabulary_level"]
    optional_deepening = audience["optional_deepening_enabled"] or knowledge["professional_supplement_enabled"]

    # Child-friendly guidance carries one low-pressure observation task unless
    # the visitor explicitly selected listen_only.  The latter is a higher
    # priority consent boundary and always wins.
    interaction_task_enabled = (
        interaction["interaction_task_enabled"]
        or (value.audience_mode == "child_friendly" and value.interaction_mode != "listen_only")
    )
    return GuidancePolicy(
        audience_mode=value.audience_mode,
        knowledge_level=value.knowledge_level,
        explanation_style=value.explanation_style,
        interaction_mode=value.interaction_mode,
        max_items_per_stop=detail["max_items_per_stop"],
        explanation_length=detail["explanation_length"],
        expansion_depth=detail["expansion_depth"],
        vocabulary_level=vocabulary_level,
        narrative_mode=STYLE_POLICY[value.explanation_style],
        interaction_task_enabled=interaction_task_enabled,
        proactive_question_enabled=interaction["proactive_question_enabled"],
        comparison_enabled=detail["comparison_enabled"],
        research_extension_enabled=detail["research_extension_enabled"],
        term_explanation_enabled=knowledge["term_explanation_enabled"],
        citation_detail=knowledge["citation_detail"],
        optional_deepening_enabled=optional_deepening,
        professional_supplement_enabled=knowledge["professional_supplement_enabled"],
        # C7 must compute min(policy target, reviewed stop budget); C6 never
        # authorizes an over-budget explanation or unsupported statement.
        fact_evidence_required=True,
        budget_cap_mode="min_with_stop_budget",
    )
