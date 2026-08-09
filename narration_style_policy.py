"""Deterministic, data-only narration style policy compiler for E5-B."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
import yaml
from guidance_policy import GuidancePolicy

STYLE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "styles_v1.yaml"
ROLE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "style_roles_v2.yaml"
STYLE_SCHEMA_VERSION = "narration_style_v2"
REQUIRED = frozenset(("schema_version", "style_id", "display_name", "applicable_policy_conditions", "vocabulary_level", "sentence_length", "narrative_pacing", "craft_explanation_style", "ornament_explanation_style", "interaction_patterns", "observation_prompt_patterns", "allowed_devices", "prohibited_patterns", "fallback_style_id", "templates"))
TEMPLATE_KEYS = frozenset(("first_craft_intro_style", "repeat_craft_style", "first_ornament_intro_style", "repeat_ornament_style"))
PLACEHOLDERS = frozenset(("craft_name", "craft_definition", "object_name", "observation_location", "visible_detail", "evidence_fact"))
REQUIRED_BASE_STYLES = frozenset(
    {"neutral", "child", "family", "student_research", "professional", "listen_only", "mixed_group"}
)
_TOKEN = re.compile(r"\{([a-z_]+)\}")

@dataclass(frozen=True)
class NarrationStylePolicy:
    style_id: str
    display_name: str
    vocabulary_level: str
    sentence_length: str
    narrative_pacing: str
    craft_explanation_style: str
    ornament_explanation_style: str
    interaction_patterns: tuple[str, ...]
    observation_prompt_patterns: tuple[str, ...]
    allowed_devices: tuple[str, ...]
    prohibited_patterns: tuple[str, ...]
    fallback_style_id: str
    templates: dict[str, str | tuple[str, ...]]
    persona: dict[str, Any] = field(default_factory=dict)
    generation_policy: dict[str, Any] = field(default_factory=dict)
    few_shot_examples: tuple[dict[str, Any], ...] = ()
    role_review_status: str = "unreviewed"


@dataclass(frozen=True)
class StyleBrief:
    """Minimal reviewed role card safe to pass to a narration realizer."""

    schema_version: str
    style_id: str
    display_name: str
    persona: dict[str, Any]
    generation_policy: dict[str, Any]
    prohibited_patterns: tuple[str, ...]
    few_shot_examples: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "style_id": self.style_id,
            "display_name": self.display_name,
            "persona": dict(self.persona),
            "generation_policy": dict(self.generation_policy),
            "prohibited_patterns": list(self.prohibited_patterns),
            "few_shot_examples": [dict(item) for item in self.few_shot_examples],
        }

def _validate(raw: dict[str, Any]) -> None:
    missing = REQUIRED - raw.keys()
    if missing or raw.get("schema_version") != "narration_style_v1":
        raise ValueError("invalid narration style schema")
    templates = raw["templates"]
    if not isinstance(templates, dict) or set(templates) != TEMPLATE_KEYS:
        raise ValueError("invalid narration style templates")
    normalized_templates: list[str] = []
    for value in templates.values():
        candidates = [value] if isinstance(value, str) else value
        if not isinstance(candidates, list) or not candidates or not all(isinstance(item, str) and item.strip() for item in candidates):
            raise ValueError("narration style templates must be a string or a non-empty string list")
        for candidate in candidates:
            if re.search(r"\bS\d+\b|source_ids|陈家祠", candidate):
                raise ValueError("template contains forbidden facts or source identifiers")
            if not set(_TOKEN.findall(candidate)).issubset(PLACEHOLDERS):
                raise ValueError("template contains invalid placeholder")
            normalized_templates.append(candidate)
    if raw["style_id"] == "listen_only" and any("?" in x or "？" in x for x in normalized_templates):
        raise ValueError("listen_only templates cannot ask questions")


def _load_reviewed_roles() -> dict[str, dict[str, Any]]:
    """Load expression-only V2 role metadata and fail closed on partial review."""
    try:
        payload = yaml.safe_load(ROLE_FILE.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != "narration_role_library_v2"
            or payload.get("review_status") != "approved"
            or not isinstance(payload.get("roles"), list)
        ):
            raise ValueError("role library is not approved v2")
        result: dict[str, dict[str, Any]] = {}
        required_persona = {
            "identity", "relationship_to_visitor", "emotional_tone",
            "speaking_perspective", "identity_boundaries",
        }
        required_policy = {
            "opening_strategy", "fact_order", "interaction_frequency",
            "rhetorical_devices", "avoid", "closing_strategy",
        }
        for raw in payload["roles"]:
            if not isinstance(raw, dict) or set(raw) != {
                "style_id", "persona", "generation_policy", "few_shot_examples",
            }:
                raise ValueError("invalid role entry")
            style_id = raw["style_id"]
            persona = raw["persona"]
            policy = raw["generation_policy"]
            examples = raw["few_shot_examples"]
            if (
                not isinstance(style_id, str)
                or style_id in result
                or not isinstance(persona, dict)
                or not required_persona.issubset(persona)
                or not isinstance(policy, dict)
                or not required_policy.issubset(policy)
                or not isinstance(examples, list)
                or not examples
            ):
                raise ValueError("incomplete reviewed role")
            if style_id == "listen_only" and (
                policy.get("interaction_frequency") != "none"
                or any(
                    mark in str(examples)
                    for mark in ("?", "？", "任务", "拍照", "试着")
                )
            ):
                raise ValueError("listen_only role violates no-interaction contract")
            result[style_id] = raw
        return result
    except (OSError, yaml.YAMLError, AttributeError, KeyError, TypeError) as exc:
        raise ValueError("narration role library unavailable") from exc

def _load_all() -> dict[str, NarrationStylePolicy]:
    try:
        payload = yaml.safe_load(STYLE_FILE.read_text(encoding="utf-8"))
        values = payload["styles"]
        if not isinstance(values, list): raise ValueError("styles must be a list")
        roles = _load_reviewed_roles()
        result: dict[str, NarrationStylePolicy] = {}
        for raw in values:
            _validate(raw)
            style_id = raw["style_id"]
            if style_id in result: raise ValueError("duplicate style id")
            normalized = {
                k: (tuple(v) if isinstance(v, list) else v)
                for k, v in raw.items()
                if k != "schema_version" and k != "applicable_policy_conditions"
            }
            normalized["templates"] = {
                key: tuple(value) if isinstance(value, list) else value
                for key, value in raw["templates"].items()
            }
            role = roles.get(style_id)
            if role is None:
                raise ValueError(f"unreviewed role: {style_id}")
            normalized.update(
                persona=dict(role["persona"]),
                generation_policy=dict(role["generation_policy"]),
                few_shot_examples=tuple(dict(item) for item in role["few_shot_examples"]),
                role_review_status="approved",
            )
            result[style_id] = NarrationStylePolicy(**normalized)
        if not REQUIRED_BASE_STYLES.issubset(result):
            raise ValueError("incomplete style set")
        for style in result.values():
            if style.fallback_style_id not in result:
                raise ValueError(f"unknown fallback style: {style.fallback_style_id}")
        if set(roles) != set(result):
            raise ValueError("role/style id mismatch")
        return result
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        raise ValueError("narration style library unavailable") from exc

def compile_narration_style(policy: GuidancePolicy) -> NarrationStylePolicy:
    """Select one style from GuidancePolicy only; never reads VisitorProfile."""
    styles = _load_all()
    if policy.interaction_mode == "listen_only": key = "listen_only"
    elif policy.audience_mode == "child_friendly": key = "child"
    elif policy.audience_mode == "family": key = "family"
    elif policy.audience_mode == "study": key = "student_research"
    elif policy.audience_mode == "mixed_group": key = "mixed_group"
    elif policy.knowledge_level == "professional" or policy.narrative_mode in {"technical", "expert"}: key = "professional"
    elif policy.narrative_mode in styles: key = policy.narrative_mode
    else: key = "neutral"
    return styles.get(key, styles["neutral"])


def resolve_narration_style_id(policy: GuidancePolicy) -> str:
    """Expose the deterministic policy-to-style decision without profile access."""
    return compile_narration_style(policy).style_id


def load_narration_style(style_id: str) -> NarrationStylePolicy:
    """Load a named style; unknown names deterministically fall back to neutral."""
    styles = _load_all()
    return styles.get(style_id, styles["neutral"])


def compile_style_brief(style_id: str) -> StyleBrief:
    """Return only the selected reviewed role; never serialize the full YAML."""
    style = load_narration_style(style_id)
    if style.role_review_status != "approved":
        style = load_narration_style("neutral")
    return StyleBrief(
        schema_version=STYLE_SCHEMA_VERSION,
        style_id=style.style_id,
        display_name=style.display_name,
        persona=dict(style.persona),
        generation_policy=dict(style.generation_policy),
        prohibited_patterns=tuple(style.prohibited_patterns),
        few_shot_examples=tuple(dict(item) for item in style.few_shot_examples),
    )


def approved_style_ids() -> tuple[str, ...]:
    """Return the complete reviewed catalog in stable authoring order."""
    return tuple(_load_all())
