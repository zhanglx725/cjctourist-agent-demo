"""D1 fail-closed registry for existing heterogeneous card files.

This module neither modifies source cards nor creates a shared vector index.
It is a deterministic validation/index layer only; caller state is never read
or written.  Existing per-type retrieval modules remain authoritative for
their own matching semantics.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

from knowledge_card_contract import KnowledgeCard, stricter_status


ROOT = Path(__file__).parent
DATA = ROOT / "data" / "chen_clan_academy"
KNOWLEDGE_ELIGIBILITY = DATA / "card_runtime_eligibility_knowledge_v1.yaml"
EXPERIENCE_ELIGIBILITY = DATA / "card_runtime_eligibility_experience_v1.yaml"
GLOSSARY = DATA / "glossary" / "glossary_zh_en_v0.yaml"
RESEARCH_DIR = DATA / "research_cards"
RESEARCH_SOURCES = RESEARCH_DIR / "research_sources_v1.json"
COMPARISONS = DATA / "comparisons" / "comparison_cards_v0.yaml"
COMPARISON_EVIDENCE = DATA / "comparisons" / "comparison_evidence_notes_v0.md"
PHOTO = DATA / "photo_spots" / "photo_spot_cards_v0.yaml"
POSE = DATA / "photo_spots" / "pose_templates_v0.yaml"
PLATFORM = DATA / "photo_spots" / "platform_observations_v0.yaml"
MARKERS = DATA / "spatial" / "marker_inventory_v0.csv"
SOURCE_REGISTRY = DATA / "sources" / "source_registry.md"


def _yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _manifest(path: Path, key: str) -> dict[str, dict[str, Any]]:
    return {
        item["card_id"]: item for item in _yaml(path).get(key, [])
        if isinstance(item, dict) and isinstance(item.get("card_id"), str)
    }


def _known_nodes() -> set[str]:
    try:
        with MARKERS.open(encoding="utf-8-sig") as handle:
            return {row["node_id"] for row in csv.DictReader(handle) if row.get("node_id")}
    except OSError:
        return set()


def _registered_sources() -> set[str]:
    try:
        return set(re.findall(r"\bS\d+\b", SOURCE_REGISTRY.read_text(encoding="utf-8")))
    except OSError:
        return set()


def _base_card(
    *, card_id: str, card_type: str, raw: dict[str, Any], eligibility: dict[str, Any] | None,
    source_refs: list[str], nodes: list[str], limitations: list[str], visitor_visible: bool = True,
    errors: list[str] | None = None, source_status: str | None = None,
) -> KnowledgeCard:
    errors = list(errors or [])
    if eligibility is None:
        errors.append("missing_eligibility")
    elif eligibility.get("card_type") != card_type:
        errors.append("eligibility_type_mismatch")
    if any(node not in _known_nodes() for node in nodes):
        errors.append("invalid_node_id")
    if not source_refs:
        errors.append("missing_source_refs")
    status = stricter_status(eligibility.get("runtime_status") if eligibility else None, source_status)
    if errors:
        status = "disabled"
    return KnowledgeCard(
        card_id=card_id, card_type=card_type, runtime_status=status,
        allowed_capabilities=tuple(eligibility.get("allowed_capabilities", [])) if eligibility else (),
        allowed_scenarios=tuple(eligibility.get("allowed_scenarios", [])) if eligibility else (),
        source_refs=tuple(source_refs), applicable_node_ids=tuple(nodes),
        limitations=tuple([*limitations, *(eligibility.get("limitations", []) if eligibility else [])]),
        raw_payload=raw, visitor_visible=visitor_visible, validation_errors=tuple(sorted(set(errors))),
    )


def build_registry() -> dict[str, KnowledgeCard]:
    """Build a fresh registry; malformed/missing inputs fail closed per card."""
    knowledge = _manifest(KNOWLEDGE_ELIGIBILITY, "cards")
    experience = _manifest(EXPERIENCE_ELIGIBILITY, "records")
    cards: dict[str, KnowledgeCard] = {}
    def add(card: KnowledgeCard) -> None:
        if card.card_id in cards:
            # Duplicate IDs cannot become usable regardless of source status.
            previous = cards[card.card_id]
            cards[card.card_id] = KnowledgeCard(**{**previous.__dict__, "runtime_status": "disabled", "validation_errors": tuple(sorted(set((*previous.validation_errors, "duplicate_card_id"))) )})
        else:
            cards[card.card_id] = card

    registered = _registered_sources()
    for raw in _yaml(GLOSSARY).get("terms", []):
        if not isinstance(raw, dict) or not raw.get("term_id"):
            continue
        refs = list(raw.get("source_ids", []))
        errors = [] if refs and set(refs).issubset(registered) else ["invalid_source_refs"]
        if raw.get("translation_status") != "reviewed" and "en_translation" in knowledge.get(raw["term_id"], {}).get("allowed_capabilities", []):
            errors.append("draft_translation_capability")
        add(_base_card(card_id=raw["term_id"], card_type="glossary_term", raw=raw,
            eligibility=knowledge.get(raw["term_id"]), source_refs=refs, nodes=[],
            limitations=["Site facts require base RAG evidence."], errors=errors,
            source_status="enabled" if raw.get("translation_status") == "reviewed" else "disabled"))

    source_index = {item.get("card_id"): item for item in _json(RESEARCH_SOURCES).get("sources", []) if isinstance(item, dict)}
    for path in RESEARCH_DIR.glob("research_*.json"):
        if path.name in {"research_sources_v1.json", "research_card_review_index_v1.json"}:
            continue
        raw = _json(path)
        card_id = raw.get("card_id")
        if not isinstance(card_id, str):
            continue
        source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
        refs = [source_index[card_id].get("source_id")] if card_id in source_index else []
        errors = [] if source.get("citation") and refs else ["invalid_source_refs"]
        if raw.get("status") == "background":
            errors.append("background_research_not_runtime")
        add(_base_card(card_id=card_id, card_type="research_summary", raw=raw,
            eligibility=knowledge.get(card_id), source_refs=[ref for ref in refs if ref],
            nodes=list(raw.get("applicable_node_ids", [])),
            limitations=[str(raw.get("agreement_and_limits", {}).get("limits", "")), "Must retain research attribution."], errors=errors,
            source_status="attributed_only" if raw.get("status") == "reviewed" else "disabled"))

    evidence_text = COMPARISON_EVIDENCE.read_text(encoding="utf-8") if COMPARISON_EVIDENCE.exists() else ""
    for raw in _yaml(COMPARISONS).get("cards", []):
        if not isinstance(raw, dict) or not raw.get("comparison_id"):
            continue
        refs = list(raw.get("source_refs", []))
        errors = [] if refs and all(ref in evidence_text for ref in refs) else ["invalid_source_refs"]
        add(_base_card(card_id=raw["comparison_id"], card_type="comparison", raw=raw,
            eligibility=knowledge.get(raw["comparison_id"]), source_refs=refs, nodes=[],
            limitations=[str(raw.get("limitations_zh", "")), "Not available in general visitor mode."], errors=errors,
            source_status="attributed_only" if raw.get("claim_strength") in {"research_only", "cautious"} else "disabled"))

    for raw in _yaml(PHOTO).get("cards", []):
        if isinstance(raw, dict) and raw.get("photo_spot_id"):
            add(_base_card(card_id=raw["photo_spot_id"], card_type="photo_spot_card", raw=raw,
                eligibility=experience.get(raw["photo_spot_id"]), source_refs=list(raw.get("evidence_refs", [])),
                nodes=[raw.get("node_id", "")], limitations=[str(raw.get("boundaries_zh", ""))],
                source_status="enabled" if raw.get("review_status") == "approved" else "disabled"))
    for raw in _yaml(POSE).get("templates", []):
        if isinstance(raw, dict) and raw.get("pose_template_id"):
            add(_base_card(card_id=raw["pose_template_id"], card_type="pose_template", raw=raw,
                eligibility=experience.get(raw["pose_template_id"]), source_refs=["editorial_pose_template"], nodes=[],
                limitations=[str(raw.get("safety_boundary_zh", ""))]))
    # Platform observations may be audited internally, but must never be a
    # visitor-facing knowledge-card result.
    for raw in _yaml(PLATFORM).get("observations", []):
        if isinstance(raw, dict) and raw.get("observation_id"):
            add(_base_card(card_id=raw["observation_id"], card_type="platform_observation", raw=raw,
                eligibility=experience.get(raw["observation_id"]), source_refs=["platform_unverified"], nodes=[],
                limitations=["Internal observation only; never visitor-facing."], visitor_visible=False,
                errors=["platform_observation_not_visitor_card"]))
    return cards


def query_registered_cards(*, card_type: str | None = None, scenario: str | None = None) -> list[KnowledgeCard]:
    """Read-only, visitor-facing query; disabled/internal cards never leak."""
    results = [card for card in build_registry().values() if card.visitor_visible and card.runtime_status != "disabled"]
    if card_type:
        results = [card for card in results if card.card_type == card_type]
    if scenario:
        results = [card for card in results if scenario in card.allowed_scenarios]
    return sorted(results, key=lambda card: card.card_id)
