"""D5-B editorial-candidate gate for optional photo recommendations.

This is deliberately a lightweight Demo gate, not a claim of full on-site
certification.  It selects only structurally safe editorial candidates.  D6
may later call this module for an explicit photo request; no generic knowledge
query, RAG path, route, or TourState path may expose these assets directly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yaml

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import DATA, EXPERIENCE_ELIGIBILITY, SOURCE_REGISTRY, _known_nodes, build_registry


EDITORIAL_ON_SITE_DISCLAIMER = "这是项目编辑整理的拍摄建议，具体可见性、光线、客流和开放情况请以现场为准。"


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
    """Return D5 editorial-candidate eligibility without changing any state.

    ``available`` means only "safe to offer as a project editorial candidate".
    It never means official, popular, fully site-verified, or currently
    photographable.
    """
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
        if card.runtime_status != "enabled" or record.get("runtime_status") != "enabled":
            reasons.append("runtime_not_editorially_enabled")
        if card.validation_errors:
            reasons.extend(card.validation_errors)
        node_id = raw.get("node_id")
        if not node_id:
            reasons.append("missing_node_id")
        elif node_id not in known_nodes:
            reasons.append("invalid_node_id")
        if not str(raw.get("boundaries_zh") or "").strip():
            reasons.append("missing_safety_boundary")
        selected_poses: list[KnowledgeCard] = []
        pose_ids = raw.get("pose_template_ids", [])
        if not pose_ids:
            reasons.append("missing_pose_template")
        for pose_id in pose_ids:
            pose = poses.get(pose_id)
            if pose is None:
                reasons.append("missing_pose_template")
            elif pose.runtime_status != "enabled":
                reasons.append("disabled_pose_template")
            elif not str(pose.raw_payload.get("safety_boundary_zh") or "").strip():
                reasons.append("pose_missing_safety_boundary")
            else:
                selected_poses.append(pose)
        for observation_id in raw.get("platform_observation_ids", []):
            if observation_id not in observations:
                reasons.append("missing_platform_observation")
            # A platform record establishes neither popularity nor a site fact.
        evidence_refs = set(raw.get("evidence_refs", []))
        if not evidence_refs or not evidence_refs.issubset(known_refs):
            reasons.append("invalid_evidence_refs")
        target_ornaments = set(raw.get("target_ornaments", []))
        if target_ornaments and not target_ornaments.issubset(ornaments_by_node.get(node_id, set())):
            reasons.append("unmapped_target_ornament")
        results[card.card_id] = {
            "available": not reasons,
            "availability_tier": "editorial_candidate" if not reasons else None,
            "reason": None if not reasons else "photo_spot_not_editorial_candidate",
            "reasons": sorted(set(reasons)),
            "node_id": node_id,
            "on_site_disclaimer_zh": EDITORIAL_ON_SITE_DISCLAIMER,
            "limitations": tuple(str(item) for item in [raw.get("boundaries_zh"), *record.get("limitations", [])] if item),
            "pose_template_ids": tuple(pose.card_id for pose in selected_poses),
        }
    return results


def query_available_photo_spots(
    *,
    node_id: str | None,
    audience_mode: str | None = None,
    themes: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Dedicated D6-ready read-only selector for explicit photo requests.

    ``audience_mode`` is accepted only as future caller context; D5-B does not
    infer audience identity or manufacture a group match.  ``themes`` may
    narrow an already valid candidate but never adds a candidate.
    """
    del audience_mode  # No visitor-profile inference at this lightweight gate.
    if not node_id:
        return {"available": False, "reason": "missing_node_id"}
    candidates = validate_photo_spot_cards()
    registry = build_registry()
    requested_themes = set(themes)
    accepted = []
    for card_id, verdict in candidates.items():
        card = registry.get(card_id)
        if not verdict["available"] or card is None or verdict["node_id"] != node_id:
            continue
        if requested_themes and not requested_themes.intersection(card.raw_payload.get("themes", [])):
            continue
        accepted.append((card_id, card, verdict))
    if not accepted:
        return {"available": False, "reason": "no_editorial_photo_candidate"}
    card_id, card, verdict = sorted(accepted, key=lambda item: item[0])[0]
    poses = []
    for pose_id in verdict["pose_template_ids"]:
        pose = registry.get(pose_id)
        if pose is not None:  # validator already established eligibility
            poses.append({
                "pose_template_id": pose.card_id,
                "title_zh": pose.raw_payload.get("title_zh"),
                "instruction_zh": pose.raw_payload.get("instruction_zh"),
                "safety_boundary_zh": pose.raw_payload.get("safety_boundary_zh"),
            })
    return {
        "available": True,
        "availability_tier": "editorial_candidate",
        "photo_spot": {
            "photo_spot_id": card_id,
            "title_zh": card.raw_payload.get("title_zh"),
            "node_id": card.raw_payload.get("node_id"),
            "themes": list(card.raw_payload.get("themes", [])),
            "target_groups": list(card.raw_payload.get("target_groups", [])),
            "editorial_label_zh": "项目编辑建议",
        },
        "pose_templates": poses,
        "limitations": [EDITORIAL_ON_SITE_DISCLAIMER, *verdict["limitations"]],
    }


def photo_spot_availability(node_id: str | None = None) -> dict[str, Any]:
    """Backward-compatible D5 availability summary; never returns draft text."""
    result = query_available_photo_spots(node_id=node_id)
    if result["available"]:
        return {"available": True, "photo_spot_ids": [result["photo_spot"]["photo_spot_id"]]}
    return result
