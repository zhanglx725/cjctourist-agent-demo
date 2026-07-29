"""Short-lived, read-only context for one controlled tour-QA follow-up.

This module deliberately does not import or mutate TourState, VisitorProfile,
or StopProgram.  It preserves only structured retrieval conditions; every
follow-up must retrieve evidence again.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "v1"
VALID_ORIGINS = frozenset({"explicit_node", "physical_deictic", "whole_site"})
VALID_SUBJECT_KINDS = frozenset({"craft", "ornament", "inventory", "fact"})
REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "query_node_id",
        "origin",
        "subject_kind",
        "subject_terms",
        "answer_mode",
        "source_response_kind",
        "follow_up_allowed",
        "physical_node_id_snapshot",
    }
)
DETAIL_FOLLOW_UP_TERMS = (
    "再讲详细",
    "详细一点",
    "详细讲讲",
    "讲细一点",
    "展开讲解",
)


def create_qa_context(
    *,
    query_node_id: str | None,
    origin: str,
    subject_kind: str,
    subject_terms: list[str] | tuple[str, ...],
    answer_mode: str,
    follow_up_allowed: bool,
    physical_node_id_snapshot: str | None,
) -> dict[str, Any]:
    """Create a validated, serializable context without retaining evidence."""
    context = {
        "schema_version": SCHEMA_VERSION,
        "query_node_id": query_node_id or None,
        "origin": origin,
        "subject_kind": subject_kind,
        "subject_terms": tuple(dict.fromkeys(str(term).strip() for term in subject_terms if str(term).strip())),
        "answer_mode": str(answer_mode),
        "source_response_kind": "tour_qa",
        "follow_up_allowed": bool(follow_up_allowed),
        "physical_node_id_snapshot": physical_node_id_snapshot or None,
    }
    validate_qa_context(context)
    return context


def validate_qa_context(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return an immutable-by-convention copy or raise ``ValueError``."""
    if not isinstance(value, dict) or set(value) != REQUIRED_FIELDS:
        raise ValueError("qa_context fields are incomplete or unexpected")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("qa_context schema_version is unsupported")
    if value.get("origin") not in VALID_ORIGINS:
        raise ValueError("qa_context origin is invalid")
    if value.get("subject_kind") not in VALID_SUBJECT_KINDS:
        raise ValueError("qa_context subject_kind is invalid")
    if value.get("source_response_kind") != "tour_qa":
        raise ValueError("qa_context source_response_kind is invalid")
    if value.get("query_node_id") is not None and not isinstance(value["query_node_id"], str):
        raise ValueError("qa_context query_node_id is invalid")
    if value.get("physical_node_id_snapshot") is not None and not isinstance(value["physical_node_id_snapshot"], str):
        raise ValueError("qa_context physical_node_id_snapshot is invalid")
    if not isinstance(value.get("subject_terms"), (tuple, list)) or not all(
        isinstance(term, str) and term for term in value["subject_terms"]
    ):
        raise ValueError("qa_context subject_terms are invalid")
    if not isinstance(value.get("answer_mode"), str) or not value["answer_mode"]:
        raise ValueError("qa_context answer_mode is invalid")
    if not isinstance(value.get("follow_up_allowed"), bool):
        raise ValueError("qa_context follow_up_allowed is invalid")
    return deepcopy(value)


def update_qa_context(value: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Return a new validated context; never mutate the supplied mapping."""
    updated = validate_qa_context(value)
    updated.update(changes)
    if "subject_terms" in updated:
        updated["subject_terms"] = tuple(
            dict.fromkeys(str(term).strip() for term in updated["subject_terms"] if str(term).strip())
        )
    validate_qa_context(updated)
    return updated


def clear_qa_context(_: dict[str, Any] | None = None) -> None:
    """Return the sole cleared representation used by graph state."""
    return None


def is_qa_follow_up_detail_request(text: str) -> bool:
    """Recognize the frozen wording without deciding which subsystem owns it."""
    return any(term in text for term in DETAIL_FOLLOW_UP_TERMS)


def is_qa_subject_follow_up_request(text: str) -> bool:
    """Recognize a short omitted-subject question such as ``石雕呢？``."""
    compact = text.strip().rstrip("？?。！!")
    if compact in {"这里呢", "此处呢", "眼前呢", "当前点呢", "当前站呢", "本点呢"}:
        return False
    return bool(compact.endswith("呢") and 1 < len(compact) <= 16)
