"""Deterministic, data-only narration style policy compiler for E5-B."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import yaml
from guidance_policy import GuidancePolicy

STYLE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "narration_styles" / "styles_v1.yaml"
STYLE_SCHEMA_VERSION = "narration_style_v1"
REQUIRED = frozenset(("schema_version", "style_id", "display_name", "applicable_policy_conditions", "vocabulary_level", "sentence_length", "narrative_pacing", "craft_explanation_style", "ornament_explanation_style", "interaction_patterns", "observation_prompt_patterns", "allowed_devices", "prohibited_patterns", "fallback_style_id", "templates"))
TEMPLATE_KEYS = frozenset(("first_craft_intro_style", "repeat_craft_style", "first_ornament_intro_style", "repeat_ornament_style"))
PLACEHOLDERS = frozenset(("craft_name", "craft_definition", "object_name", "observation_location", "visible_detail", "evidence_fact"))
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
    templates: dict[str, str]

def _validate(raw: dict[str, Any]) -> None:
    missing = REQUIRED - raw.keys()
    if missing or raw.get("schema_version") != "narration_style_v1":
        raise ValueError("invalid narration style schema")
    templates = raw["templates"]
    if not isinstance(templates, dict) or set(templates) != TEMPLATE_KEYS:
        raise ValueError("invalid narration style templates")
    for value in templates.values():
        if not isinstance(value, str) or re.search(r"\bS\d+\b|source_ids|陈家祠", value):
            raise ValueError("template contains forbidden facts or source identifiers")
        if not set(_TOKEN.findall(value)).issubset(PLACEHOLDERS):
            raise ValueError("template contains invalid placeholder")
    if raw["style_id"] == "listen_only" and any("?" in x or "？" in x for x in templates.values()):
        raise ValueError("listen_only templates cannot ask questions")

def _load_all() -> dict[str, NarrationStylePolicy]:
    try:
        payload = yaml.safe_load(STYLE_FILE.read_text(encoding="utf-8"))
        values = payload["styles"]
        if not isinstance(values, list): raise ValueError("styles must be a list")
        result: dict[str, NarrationStylePolicy] = {}
        for raw in values:
            _validate(raw)
            style_id = raw["style_id"]
            if style_id in result: raise ValueError("duplicate style id")
            result[style_id] = NarrationStylePolicy(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in raw.items() if k != "schema_version" and k != "applicable_policy_conditions"})
        if set(result) != {"neutral", "child", "family", "student_research", "professional", "listen_only", "mixed_group"}:
            raise ValueError("incomplete style set")
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
    else: key = "neutral"
    return styles.get(key, styles["neutral"])


def resolve_narration_style_id(policy: GuidancePolicy) -> str:
    """Expose the deterministic policy-to-style decision without profile access."""
    return compile_narration_style(policy).style_id


def load_narration_style(style_id: str) -> NarrationStylePolicy:
    """Load a named style; unknown names deterministically fall back to neutral."""
    styles = _load_all()
    return styles.get(style_id, styles["neutral"])
