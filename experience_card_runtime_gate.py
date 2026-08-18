"""Closed runtime gate for experience-card data.

This module deliberately has no Agent, route, RAG, or tour-state integration.
It exposes only approved records from the D0-E eligibility manifest.  Missing
or malformed eligibility data fail closed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).parent
EXPERIENCE_DIR = ROOT / "data" / "chen_clan_academy"
ELIGIBILITY_FILE = EXPERIENCE_DIR / "card_runtime_eligibility_experience_v1.yaml"
PHOTO_FILE = EXPERIENCE_DIR / "photo_spots" / "photo_spot_cards_v0.yaml"
POSE_FILE = EXPERIENCE_DIR / "photo_spots" / "pose_templates_v0.yaml"
PLATFORM_FILE = EXPERIENCE_DIR / "photo_spots" / "platform_observations_v0.yaml"

NO_APPROVED_CONTENT = "暂无可用内容"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_eligibility_records() -> dict[str, dict[str, Any]]:
    """Load records by ID. Missing IDs are intentionally unavailable."""
    records = _load_yaml(ELIGIBILITY_FILE).get("records", [])
    return {
        item["card_id"]: item
        for item in records
        if isinstance(item, dict) and isinstance(item.get("card_id"), str)
    }


def _approved_records(card_type: str, source_items: list[dict[str, Any]], id_field: str) -> list[dict[str, Any]]:
    eligibility = load_eligibility_records()
    selected: list[dict[str, Any]] = []
    for item in source_items:
        card_id = item.get(id_field)
        record = eligibility.get(card_id)
        # A missing record, mismatched type, or any non-enabled state fails closed.
        if not record or record.get("card_type") != card_type or record.get("runtime_status") != "enabled":
            continue
        selected.append(item)
    return selected


def select_photo_spot_cards(node_id: str | None = None) -> dict[str, Any]:
    cards = _load_yaml(PHOTO_FILE).get("cards", [])
    cards = [item for item in cards if isinstance(item, dict)]
    if node_id:
        cards = [item for item in cards if item.get("node_id") == node_id]
    selected = _approved_records("photo_spot_card", cards, "photo_spot_id")
    return {
        "status": "ok" if selected else "no_approved_content",
        "message_zh": "" if selected else NO_APPROVED_CONTENT,
        "cards": selected,
    }


def select_pose_templates() -> dict[str, Any]:
    templates = _load_yaml(POSE_FILE).get("templates", [])
    templates = [item for item in templates if isinstance(item, dict)]
    selected = _approved_records("pose_template", templates, "pose_template_id")
    return {
        "status": "ok" if selected else "no_approved_content",
        "message_zh": "" if selected else NO_APPROVED_CONTENT,
        "cards": selected,
    }


def select_platform_observations() -> dict[str, Any]:
    observations = _load_yaml(PLATFORM_FILE).get("observations", [])
    observations = [item for item in observations if isinstance(item, dict)]
    selected = _approved_records("platform_observation", observations, "observation_id")
    return {
        "status": "ok" if selected else "no_approved_content",
        "message_zh": "" if selected else NO_APPROVED_CONTENT,
        "cards": selected,
    }
