"""D5-B fail-closed runtime validation for experience/photo cards.

This module is deliberately not a recommender.  It validates whether an
already manually reviewed card may *later* be exposed; it never upgrades a
draft, pose template, or platform observation itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import DATA, EXPERIENCE_ELIGIBILITY, SOURCE_REGISTRY, _known_nodes, build_registry


REQUIRED_VERIFICATIONS = (
    "location_verification_status",
    "safety_verification_status",
    "content_verification_status",
    "source_verification_status",
)


def _experience_records(path: Path = EXPERIENCE_ELIGIBILITY) -> dict[str, dict[str, Any]]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {
        item["card_id"]: item for item in document.get("records", [])
        if isinstance(item, dict) and isinstance(item.get("card_id"), str)
    }


def _known_evidence_refs() -> set[str]:
    refs: set[str] = set()
    try:
        refs.update(re.findall(r"\bS\d+\b", SOURCE_REGISTRY.read_text(encoding="utf-8")))
    except OSError:
        pass
    comparison_notes = DATA / "comparisons" / "comparison_evidence_notes_v0.md"
    try:
        refs.update(re.findall(r"\bCMPREF_[A-Z0-9_]+\b", comparison_notes.read_text(encoding="utf-8")))
    except OSError:
        pass
    return refs


def _guide_ornaments_by_node() -> dict[str, set[str]]:
    path = DATA / "routes" / "node_guide_cards_v1.json"
    try:
        import json
        cards = json.loads(path.read_text(encoding="utf-8")).get("cards", [])
    except (OSError, ValueError):
        return {}
    return {
        card.get("node_id"): {item.get("name") for item in card.get("ornaments", []) if item.get("name")}
        for card in cards if isinstance(card, dict) and card.get("node_id")
    }


def validate_photo_spot_cards(
    *,
    registry_loader: Callable[[], dict[str, KnowledgeCard]] = build_registry,
    eligibility_loader: Callable[[], dict[str, dict[str, Any]]] = _experience_records,
    evidence_refs_loader: Callable[[], set[str]] = _known_evidence_refs,
    ornaments_loader: Callable[[], dict[str, set[str]]] = _guide_ornaments_by_node,
) -> dict[str, dict[str, Any]]:
    """Return one fail-closed validation result per photo spot without writes."""
    try:
        registry = registry_loader()
        records = eligibility_loader()
        known_refs = evidence_refs_loader()
        ornaments_by_node = ornaments_loader()
    except Exception:
        return {}
    known_nodes = _known_nodes()
    poses = {card.card_id: card for card in registry.values() if card.card_type == "pose_template"}
    observations = {card.card_id: card for card in registry.values() if card.card_type == "platform_observation"}
    results: dict[str, dict[str, Any]] = {}
    for card in registry.values():
        if card.card_type != "photo_spot_card":
            continue
        raw = card.raw_payload
        record = records.get(card.card_id, {})
        reasons: list[str] = []
        if card.runtime_status != "enabled":
            reasons.append("runtime_not_enabled")
        if record.get("runtime_status") != "enabled":
            reasons.append("eligibility_runtime_not_enabled")
        for field in REQUIRED_VERIFICATIONS:
            if record.get(field) != "verified":
                reasons.append(f"{field}_not_verified")
        if not record.get("reviewer"):
            reasons.append("missing_reviewer")
        if not record.get("reviewed_at"):
            reasons.append("missing_reviewed_at")
        if record.get("blocking_issues") not in (None, [], ""):
            reasons.append("blocking_issues_present")
        if raw.get("review_status") != "approved":
            reasons.append("card_not_manually_approved")
        if raw.get("popularity_status") == "editorial_recommended":
            reasons.append("editorial_recommended_not_popularity_evidence")
        if card.validation_errors:
            reasons.extend(card.validation_errors)
        node_id = raw.get("node_id")
        if not node_id:
            reasons.append("missing_node_id")
        elif node_id not in known_nodes:
            reasons.append("invalid_node_id")
        for pose_id in raw.get("pose_template_ids", []):
            pose = poses.get(pose_id)
            if pose is None:
                reasons.append("missing_pose_template")
            elif pose.runtime_status != "enabled":
                reasons.append("disabled_pose_template")
        for observation_id in raw.get("platform_observation_ids", []):
            if observation_id not in observations:
                reasons.append("missing_platform_observation")
            # Existing observations are deliberately never evidence or a way
            # to turn editorial guidance into a 'popular' claim.
        evidence_refs = set(raw.get("evidence_refs", []))
        if not evidence_refs or not evidence_refs.issubset(known_refs):
            reasons.append("invalid_evidence_refs")
        target_ornaments = set(raw.get("target_ornaments", []))
        if target_ornaments:
            mapped = ornaments_by_node.get(node_id, set())
            if not target_ornaments.issubset(mapped):
                reasons.append("unmapped_target_ornament")
        results[card.card_id] = {
            "available": not reasons,
            "reason": None if not reasons else "photo_spot_not_runtime_eligible",
            "reasons": sorted(set(reasons)),
            "node_id": node_id,
        }
    return results


def photo_spot_availability(node_id: str | None = None) -> dict[str, Any]:
    """Reserved D6-shaped result; D5-B never returns draft content."""
    results = validate_photo_spot_cards()
    available = [card_id for card_id, result in results.items() if result["available"] and (not node_id or result["node_id"] == node_id)]
    if not available:
        return {"available": False, "reason": "no_reviewed_photo_spot"}
    return {"available": True, "photo_spot_ids": sorted(available)}
