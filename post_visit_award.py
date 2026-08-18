"""Deterministic P4-03 title policy backed by the approved human catalog."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from string import Formatter
from typing import Any

import yaml


POLICY_VERSION = "post_visit_award_policy_v2"
CATALOG_FILE = (
    Path(__file__).parent
    / "data" / "chen_clan_academy" / "evaluation" / "manual_reviews"
    / "p4_03_title_catalog_authoring_template_v1.yaml"
)
EXPECTED_CATEGORIES = frozenset({
    "curious_explorer", "interest_connoisseur", "many_arts_wanderer",
    "story_tracer", "route_finisher", "mindful_visitor",
})
REQUIRED_CANDIDATE_FIELDS = frozenset({
    "candidate_id", "title_zh", "reason_template_zh", "blessing_template_zh",
    "review_status", "enabled",
})
_ROTATION_TERMS = (
    "换一个称号", "换个称号", "再来一个称号", "再来个称号",
    "另一个称号", "不同的称号", "换一个祝福", "换个祝福",
)
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class PostVisitAwardError(ValueError):
    pass


def is_post_visit_request(text: str) -> bool:
    compact = "".join(str(text or "").split()).rstrip("。！!？?")
    return any(term in compact for term in (
        "称号", "祝福", "游览总结", "参观总结", "看看总结", "查看总结",
    ))


def is_title_rotation_request(text: str) -> bool:
    compact = "".join(str(text or "").split()).rstrip("。！!？?")
    return any(term in compact for term in _ROTATION_TERMS)


def _template_fields(value: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(value)
        if field_name is not None
    }


def load_post_visit_title_catalog() -> dict[str, Any]:
    """Load and fail closed on malformed, unreviewed or unsafe catalog data."""
    try:
        payload = yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PostVisitAwardError("称号候选库不可用。") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "post_visit_title_catalog_authoring_v1":
        raise PostVisitAwardError("称号候选库版本无效。")
    policy = payload.get("global_policy")
    categories = payload.get("categories")
    if not isinstance(policy, dict) or not isinstance(categories, list):
        raise PostVisitAwardError("称号候选库结构无效。")
    allowed_placeholders = set(policy.get("allowed_placeholders") or [])
    title_bounds = policy.get("title_length_zh") or {}
    minimum = title_bounds.get("min_characters")
    maximum = title_bounds.get("max_characters")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum > maximum:
        raise PostVisitAwardError("称号长度规则无效。")

    category_ids: set[str] = set()
    candidate_ids: set[str] = set()
    approved_by_category: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        if not isinstance(category, dict) or not isinstance(category.get("candidates"), list):
            raise PostVisitAwardError("称号类别结构无效。")
        category_id = category.get("category_id")
        if category_id in category_ids or category_id not in EXPECTED_CATEGORIES:
            raise PostVisitAwardError("称号类别 ID 无效或重复。")
        category_ids.add(category_id)
        approved: list[dict[str, Any]] = []
        for candidate in category["candidates"]:
            if not isinstance(candidate, dict) or REQUIRED_CANDIDATE_FIELDS - candidate.keys():
                raise PostVisitAwardError("称号候选字段不完整。")
            candidate_id = candidate.get("candidate_id")
            title = candidate.get("title_zh")
            if not isinstance(candidate_id, str) or not _ID.fullmatch(candidate_id) or candidate_id in candidate_ids:
                raise PostVisitAwardError("称号候选 ID 无效或重复。")
            candidate_ids.add(candidate_id)
            if not isinstance(title, str) or not minimum <= len(title.strip()) <= maximum:
                raise PostVisitAwardError(f"称号长度无效：{candidate_id}")
            for key in ("reason_template_zh", "blessing_template_zh"):
                template = candidate.get(key)
                if not isinstance(template, str) or not template.strip():
                    raise PostVisitAwardError(f"称号模板无效：{candidate_id}")
                if not _template_fields(template).issubset(allowed_placeholders):
                    raise PostVisitAwardError(f"称号模板占位符无效：{candidate_id}")
            if candidate.get("review_status") == "approved" and candidate.get("enabled") is True:
                approved.append(deepcopy(candidate))
        if not approved:
            raise PostVisitAwardError(f"称号类别没有可用候选：{category_id}")
        approved_by_category[category_id] = approved
    if category_ids != EXPECTED_CATEGORIES:
        raise PostVisitAwardError("称号类别集合不完整。")
    return {
        "catalog_version": payload.get("catalog_version"),
        "disclaimer": policy.get("public_disclaimer_zh"),
        "approved_by_category": approved_by_category,
    }


def _validated_basis(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, dict) or summary.get("schema_version") != "visit_summary_v1":
        raise PostVisitAwardError("游览总结不可用。")
    basis = summary.get("title_basis")
    if not isinstance(basis, dict):
        raise PostVisitAwardError("称号依据不可用。")
    return basis


def _category_from_basis(basis: dict[str, Any]) -> str:
    question_count = basis.get("question_count")
    question_count = question_count if isinstance(question_count, int) and question_count >= 0 else None
    matched = tuple(item for item in basis.get("matched_interest_ids") or [] if isinstance(item, str) and item)
    topics = tuple(item for item in basis.get("introduced_topic_names") or [] if isinstance(item, str) and item)
    diversity = basis.get("content_diversity_count")
    diversity = diversity if isinstance(diversity, int) and diversity >= 0 else 0
    completed = basis.get("completion_kind") == "completed_all_stops"
    visited = basis.get("visited_stop_count")
    visited = visited if isinstance(visited, int) and visited >= 0 else 0
    if question_count is not None and question_count >= 3:
        return "curious_explorer"
    if len(matched) >= 2:
        return "interest_connoisseur"
    if diversity >= 5:
        return "many_arts_wanderer"
    if basis.get("explanation_style") == "story" and len(topics) >= 2:
        return "story_tracer"
    if completed and visited >= 2:
        return "route_finisher"
    return "mindful_visitor"


def _render_values(basis: dict[str, Any]) -> dict[str, Any]:
    def joined(key: str, fallback: str) -> str:
        values = [item for item in basis.get(key) or [] if isinstance(item, str) and item]
        return "、".join(values) if values else fallback

    return {
        "question_count": basis.get("question_count", 0),
        "visited_stop_count": basis.get("visited_stop_count", 0),
        "matched_interests": joined("matched_interest_ids", "本轮明确关注的内容"),
        "introduced_crafts": joined("introduced_craft_ids", "已讲解工艺"),
        "introduced_topics": joined("introduced_topic_names", "已讲解题材"),
        "explanation_style": basis.get("explanation_style") or "中性",
        "language": basis.get("language") or "本轮讲解语言",
    }


def build_post_visit_award(
    summary: dict[str, Any] | None,
    *,
    variant_cursor: int = 0,
) -> dict[str, Any]:
    """Select one approved candidate from the frozen same-category order."""
    basis = _validated_basis(summary)
    if isinstance(variant_cursor, bool) or not isinstance(variant_cursor, int) or variant_cursor < 0:
        raise PostVisitAwardError("称号轮换游标无效。")
    catalog = load_post_visit_title_catalog()
    category_id = _category_from_basis(basis)
    candidates = catalog["approved_by_category"][category_id]
    normalized_cursor = variant_cursor % len(candidates)
    candidate = candidates[normalized_cursor]
    values = _render_values(basis)
    try:
        reason = candidate["reason_template_zh"].format_map(values)
        blessing = candidate["blessing_template_zh"].format_map(values)
    except (KeyError, ValueError) as exc:
        raise PostVisitAwardError("称号模板渲染失败。") from exc
    return {
        "schema_version": "post_visit_award_v1",
        "policy_version": POLICY_VERSION,
        "catalog_version": catalog["catalog_version"],
        # title_id remains the stable rule/category ID for compatibility.
        "title_id": category_id,
        "category_id": category_id,
        "candidate_id": candidate["candidate_id"],
        "variant_cursor": normalized_cursor,
        "approved_candidate_count": len(candidates),
        "title": candidate["title_zh"],
        "reason": reason,
        "blessing": blessing,
        "disclaimer": catalog["disclaimer"],
        "basis_snapshot": deepcopy(basis),
    }
