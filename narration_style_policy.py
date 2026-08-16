"""Deterministic, data-only narration style policy compiler for E5-B."""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
import yaml
from guidance_policy import GuidancePolicy

STYLE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "styles_v1.yaml"
ROLE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "style_roles_v2.yaml"
POINT_COMPONENT_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "point_narration_components_v1.yaml"
COMPACT_COMPONENT_KEYS = frozenset({
    "compact_opening", "compact_appreciation", "compact_closing",
    *(f"{topic}_micro_{kind}" for topic in ("space", "craft", "ornament")
      for kind in ("observation", "transition")),
    "definition_bridge", "process_bridge", "object_bridge", "story_bridge",
})
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
    # Reviewed, expression-only acceptance criteria.  Generation and
    # validation consume this in later stages; loading it here makes the role
    # card a single executable source of truth without changing current
    # visitor-visible behaviour.
    acceptance_profile: dict[str, Any] = field(default_factory=dict)
    few_shot_examples: tuple[dict[str, Any], ...] = ()
    point_narration_components: dict[str, tuple[str, ...]] = field(default_factory=dict)
    role_review_status: str = "unreviewed"


@dataclass(frozen=True)
class StyleBrief:
    """Minimal reviewed role card safe to pass to a narration realizer."""

    schema_version: str
    style_id: str
    display_name: str
    persona: dict[str, Any]
    generation_policy: dict[str, Any]
    acceptance_profile: dict[str, Any]
    prohibited_patterns: tuple[str, ...]
    few_shot_examples: tuple[dict[str, Any], ...]
    point_narration_components: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "style_id": self.style_id,
            "display_name": self.display_name,
            "persona": dict(self.persona),
            "generation_policy": dict(self.generation_policy),
            "acceptance_profile": dict(self.acceptance_profile),
            "prohibited_patterns": list(self.prohibited_patterns),
            "few_shot_examples": [dict(item) for item in self.few_shot_examples],
            "point_narration_components": {
                key: list(values) for key, values in self.point_narration_components.items()
            },
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
            payload.get("schema_version") != "narration_role_library_v3"
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
        required_acceptance = {
            "required_markers", "forbidden_markers", "rhythm",
            "interaction_contract", "point_narration_strategy",
        }
        for raw in payload["roles"]:
            if not isinstance(raw, dict) or set(raw) != {
                "style_id", "persona", "generation_policy", "acceptance_profile",
                "few_shot_examples",
            }:
                raise ValueError("invalid role entry")
            style_id = raw["style_id"]
            persona = raw["persona"]
            policy = raw["generation_policy"]
            acceptance = raw["acceptance_profile"]
            examples = raw["few_shot_examples"]
            if (
                not isinstance(style_id, str)
                or style_id in result
                or not isinstance(persona, dict)
                or not required_persona.issubset(persona)
                or not isinstance(policy, dict)
                or not required_policy.issubset(policy)
                or not isinstance(acceptance, dict)
                or not required_acceptance.issubset(acceptance)
                or not isinstance(acceptance["required_markers"], list)
                or not acceptance["required_markers"]
                or not isinstance(acceptance["forbidden_markers"], list)
                or not isinstance(acceptance["rhythm"], dict)
                or not isinstance(acceptance["interaction_contract"], dict)
                or not isinstance(acceptance["point_narration_strategy"], list)
                or not acceptance["point_narration_strategy"]
                or not isinstance(examples, list)
                or len(examples) < 3
            ):
                raise ValueError("incomplete reviewed role")
            if style_id == "listen_only" and (
                policy.get("interaction_frequency") != "none"
                or acceptance["interaction_contract"].get("mode") != "none"
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


def _load_point_narration_components() -> dict[str, dict[str, tuple[str, ...]]]:
    """Load reviewed, fact-free phrases for fact-block interleaving."""
    required = {
        "opening", "appreciation", "closing",
        *(f"{topic}_{kind}" for topic in ("space", "craft", "ornament")
          for kind in ("intro", "observation", "transition")),
    }
    try:
        payload = yaml.safe_load(POINT_COMPONENT_FILE.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") != "point_narration_components_v2"
            or payload.get("review_status") != "approved"
            or payload.get("layout") != "continuous_narration"
            or not isinstance(payload.get("roles"), dict)
        ):
            raise ValueError("point narration components are not approved")
        result: dict[str, dict[str, tuple[str, ...]]] = {}
        for style_id, raw in payload["roles"].items():
            raw_keys = set(raw) if isinstance(raw, dict) else set()
            if (
                not isinstance(style_id, str)
                or not isinstance(raw, dict)
                or not required.issubset(raw_keys)
                or raw_keys - required - COMPACT_COMPONENT_KEYS
                or (raw_keys & COMPACT_COMPONENT_KEYS and not COMPACT_COMPONENT_KEYS.issubset(raw_keys))
            ):
                raise ValueError("invalid point narration component entry")
            components: dict[str, tuple[str, ...]] = {}
            for key in raw_keys:
                values = raw[key]
                if (
                    not isinstance(values, list)
                    or len(values) < (3 if key in COMPACT_COMPONENT_KEYS else 2)
                    or not all(isinstance(value, str) and value.strip() for value in values)
                ):
                    raise ValueError("incomplete point narration component")
                # Components are expression-only.  Reject accidental internal
                # references and venue-specific claims at the source boundary.
                if any(re.search(r"(?:source|node|route|http|www\\.|\\d{3,4}年)", value, re.I) for value in values):
                    raise ValueError("point narration component contains non-expression content")
                if any(re.search(r"(?:～|。。|，，|,,|\n|【|】|^\s*(?:#|[-*+]\s|\d+[.)、]))", value) for value in values):
                    raise ValueError("point narration component violates continuous layout")
                components[key] = tuple(values)
            result[style_id] = components
        return result
    except (OSError, yaml.YAMLError, AttributeError, KeyError, TypeError) as exc:
        raise ValueError("point narration component library unavailable") from exc

@lru_cache(maxsize=1)
def _load_all() -> dict[str, NarrationStylePolicy]:
    try:
        payload = yaml.safe_load(STYLE_FILE.read_text(encoding="utf-8"))
        values = payload["styles"]
        if not isinstance(values, list): raise ValueError("styles must be a list")
        roles = _load_reviewed_roles()
        point_components = _load_point_narration_components()
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
            components = point_components.get(style_id)
            if components is None:
                raise ValueError(f"unreviewed point narration components: {style_id}")
            normalized.update(
                persona=dict(role["persona"]),
                generation_policy=dict(role["generation_policy"]),
                acceptance_profile=dict(role["acceptance_profile"]),
                few_shot_examples=tuple(dict(item) for item in role["few_shot_examples"]),
                point_narration_components=components,
                role_review_status="approved",
            )
            interaction_mode = str(role["acceptance_profile"]["interaction_contract"].get("mode") or "none")
            if interaction_mode == "none" and any(
                re.search(r"[?？]|(?:请|试着|拍|站|走|找一找)", phrase)
                for values in components.values() for phrase in values
            ):
                raise ValueError(f"non-interactive point components request action: {style_id}")
            result[style_id] = NarrationStylePolicy(**normalized)
        if not REQUIRED_BASE_STYLES.issubset(result):
            raise ValueError("incomplete style set")
        for style in result.values():
            if style.fallback_style_id not in result:
                raise ValueError(f"unknown fallback style: {style.fallback_style_id}")
        if set(roles) != set(result):
            raise ValueError("role/style id mismatch")
        if set(point_components) != set(result):
            raise ValueError("point narration component/style id mismatch")
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
        acceptance_profile=dict(style.acceptance_profile),
        prohibited_patterns=tuple(style.prohibited_patterns),
        few_shot_examples=tuple(dict(item) for item in style.few_shot_examples),
        point_narration_components={
            key: tuple(values) for key, values in style.point_narration_components.items()
        },
    )


def approved_style_ids() -> tuple[str, ...]:
    """Return the complete reviewed catalog in stable authoring order."""
    return tuple(_load_all())
