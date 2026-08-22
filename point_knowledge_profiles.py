"""Reviewed point-to-knowledge hints for optional stop narration context."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any


PROFILE_FILE = Path(__file__).parent / "data" / "chen_clan_academy" / "routes" / "point_knowledge_profiles_v1.json"
OPTIONAL_DOCUMENTS = frozenset({
    "02_history_architecture.md",
    "10_people_builders_craftspeople.md",
    "11_architectural_conservation.md",
    "12_craft_process_and_transmission.md",
    "13_literary_citation_cards.md",
    "14_students_examinations_and_education.md",
})


@dataclass(frozen=True)
class PointKnowledgeProfile:
    node_id: str
    excluded_objects: tuple[str, ...]
    visible_components: tuple[str, ...]
    optional_dimensions: tuple[str, ...]
    next_stop_preview: tuple[str, ...]


def _clean_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("point knowledge list field must be a list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if len(result) != len(value):
        raise ValueError("point knowledge list field contains an empty value")
    return result


@lru_cache(maxsize=1)
def load_point_knowledge_profiles() -> dict[str, PointKnowledgeProfile]:
    raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "v1" or not isinstance(raw.get("profiles"), list):
        raise ValueError("unsupported point knowledge profile schema")
    profiles: dict[str, PointKnowledgeProfile] = {}
    for item in raw["profiles"]:
        node_id = str(item.get("node_id") or "").strip()
        if not node_id or node_id in profiles:
            raise ValueError("point knowledge profile node_id must be unique")
        profiles[node_id] = PointKnowledgeProfile(
            node_id=node_id,
            excluded_objects=_clean_strings(item.get("excluded_objects", [])),
            visible_components=_clean_strings(item.get("visible_components")),
            optional_dimensions=_clean_strings(item.get("optional_dimensions")),
            next_stop_preview=_clean_strings(item.get("next_stop_preview")),
        )
    return profiles


def point_knowledge_profile(node_id: str) -> PointKnowledgeProfile | None:
    return load_point_knowledge_profiles().get(node_id)


def optional_context_query(
    node_id: str,
    display_name: str,
    *,
    object_names: tuple[str, ...],
    crafts: tuple[str, ...],
) -> str | None:
    profile = point_knowledge_profile(node_id)
    if profile is None:
        return None
    terms = (
        display_name,
        *object_names,
        *crafts,
        *profile.visible_components,
        *profile.optional_dimensions,
    )
    return " ".join(dict.fromkeys(term for term in terms if term))
