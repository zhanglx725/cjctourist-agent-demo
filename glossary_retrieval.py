"""Read reviewed point-to-glossary associations as RAG query hints.

Glossary cards improve terminology recall and bilingual consistency.  They are
not a substitute for RAG evidence and must never be rendered as unverified
on-site facts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).parent
GLOSSARY_FILE = ROOT / "data" / "chen_clan_academy" / "glossary" / "glossary_zh_en_v0.yaml"
ASSOCIATIONS_FILE = ROOT / "data" / "chen_clan_academy" / "routes" / "term_stop_associations_v1.json"


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
