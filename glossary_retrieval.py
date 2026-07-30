"""Read reviewed point-to-glossary associations as RAG query hints.

Glossary cards improve terminology recall and bilingual consistency.  They are
not a substitute for RAG evidence and must never be rendered as unverified
on-site facts.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).parent
GLOSSARY_FILE = ROOT / "data" / "chen_clan_academy" / "glossary" / "glossary_zh_en_v0.yaml"
ASSOCIATIONS_FILE = ROOT / "data" / "chen_clan_academy" / "routes" / "term_stop_associations_v1.json"
NODE_GUIDE_CARDS_FILE = ROOT / "data" / "chen_clan_academy" / "routes" / "node_guide_cards_v1.json"


@lru_cache(maxsize=1)
def load_glossary() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(GLOSSARY_FILE.read_text(encoding="utf-8")) or {}
    return {item["term_id"]: item for item in data.get("terms", []) if item.get("term_id")}


@lru_cache(maxsize=1)
def load_associations() -> dict[str, list[dict[str, Any]]]:
    if not ASSOCIATIONS_FILE.exists():
        return {}
    data = json.loads(ASSOCIATIONS_FILE.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in data.get("associations", []):
        node_id = item.get("node_id")
        if node_id and item.get("term_id"):
            grouped.setdefault(node_id, []).append(item)
    return grouped


@lru_cache(maxsize=1)
def load_node_guide_cards() -> dict[str, dict[str, Any]]:
    """Read the reviewed node cards used to validate association evidence."""
    try:
        data = json.loads(NODE_GUIDE_CARDS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        card["node_id"]: card
        for card in data.get("cards", [])
        if isinstance(card, dict) and isinstance(card.get("node_id"), str)
    }


def _association_ornament_id(association: dict[str, Any]) -> str | None:
    """Extract only the reviewed ornament ID carried by the association evidence."""
    evidence = association.get("evidence")
    if not isinstance(evidence, str):
        return None
    match = re.match(r"^(orn_\d+)\s+\(", evidence)
    return match.group(1) if match else None


def reviewed_term_instances(
    term_id: str,
    *,
    current_node_id: str | None = None,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` audited term-to-object examples.

    An association is enough to rank a terminology card, but it becomes a
    visitor-facing object example only when its evidence names an ornament that
    is present in the same reviewed node card and the relationship is explicitly
    ``direct_craft_observation``.  Context-only associations deliberately stay
    out of this list: they do not prove that the named object exemplifies the
    queried term.
    """
    if limit <= 0:
        return []
    glossary = load_glossary()
    term = glossary.get(term_id)
    if not term:
        return []
    term_zh = term.get("zh")
    if not isinstance(term_zh, str) or not term_zh:
        return []
    node_cards = load_node_guide_cards()
    candidates: list[dict[str, Any]] = []
    for node_id, associations in load_associations().items():
        node_card = node_cards.get(node_id)
        if not node_card:
            continue
        for association in associations:
            if (
                association.get("term_id") != term_id
                or association.get("association_type") != "direct_craft_observation"
                or association.get("status") != "derived_from_approved_ornament_mapping"
            ):
                continue
            ornament_id = _association_ornament_id(association)
            ornament = next(
                (
                    item for item in node_card.get("ornaments", [])
                    if isinstance(item, dict) and item.get("ornament_id") == ornament_id
                ),
                None,
            )
            if not ornament or ornament.get("craft") != term_zh or not ornament.get("name"):
                continue
            raw_location = ornament.get("raw_location")
            if not isinstance(raw_location, str) or not raw_location.strip():
                continue
            candidates.append(
                {
                    "term_id": term_id,
                    "node_id": node_id,
                    "point_name": node_card.get("display_name") or node_id,
                    "ornament_id": ornament_id,
                    "ornament_name": ornament["name"],
                    "craft": ornament["craft"],
                    # Retained only for internal audit.  Visitor formatting
                    # intentionally never emits this raw source field.
                    "raw_location": raw_location,
                    "association_type": association["association_type"],
                    "association_evidence": association.get("evidence"),
                }
            )
    candidates.sort(
        key=lambda item: (
            item["node_id"] != current_node_id,
            item["node_id"],
            item["ornament_id"],
        )
    )
    return candidates[:limit]


def point_glossary_context(node_id: str | None, user_query: str = "") -> dict[str, Any]:
    """Return reviewed, point-specific term hints without asserting facts."""
    if not node_id:
        return {"status": "no_current_stop", "terms": []}
    if not ASSOCIATIONS_FILE.exists():
        return {"status": "associations_not_generated", "terms": []}

    glossary = load_glossary()
    query = user_query.casefold()
    terms: list[dict[str, Any]] = []
    for association in load_associations().get(node_id, []):
        card = glossary.get(association["term_id"])
        if not card:
            continue
        aliases = [card.get("zh", ""), *card.get("aliases_zh", []), *card.get("aliases_en", [])]
        matched = any(alias and alias.casefold() in query for alias in aliases)
        terms.append(
            {
                "term_id": card["term_id"],
                "zh": card.get("zh"),
                "en": card.get("en"),
                "domain": card.get("domain"),
                "association_type": association.get("association_type"),
                "matched_in_query": matched,
            }
        )
    terms.sort(key=lambda item: (not item["matched_in_query"], item["zh"] or ""))
    return {"status": "ok", "terms": terms}


def format_point_glossary_hint(node_id: str | None, user_query: str = "", limit: int = 8) -> str:
    """Format compact retrieval-only hints for the existing RAG query."""
    context = point_glossary_context(node_id, user_query)
    terms = context["terms"]
    if not terms:
        return ""
    selected = terms[:limit]
    labels = "、".join(
        f"{item['zh']}（{item['en']}）" if item.get("en") else str(item["zh"])
        for item in selected
    )
    return f"当前点位已审核关联术语提示：{labels}。仅用于缩小检索范围，最终事实仍须来自 RAG evidence。"
