"""Thread-local, non-factual control state for same-name ornament choices."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


SCHEMA_VERSION = "v1"


def create_pending_ornament_clarification(
    *,
    original_query: str,
    subject_name: str,
    candidates: Iterable[dict[str, Any]],
    requested_detail: str,
    evidence_scope: str,
) -> dict[str, Any]:
    """Return validated, serializable choice state without adding facts."""
    normalized = [deepcopy(candidate) for candidate in candidates]
    if len(normalized) < 2:
        raise ValueError("clarification needs at least two candidate categories")
    if not original_query.strip() or not subject_name.strip():
        raise ValueError("clarification query and subject are required")
    if requested_detail not in {"story", "detail"}:
        raise ValueError("unsupported requested detail")
    if evidence_scope not in {"exact_ornament", "craft_only"}:
        raise ValueError("unsupported evidence scope")
    for index, candidate in enumerate(normalized, start=1):
        if candidate.get("choice_index") != index:
            raise ValueError("candidate indexes must be stable and contiguous")
        if candidate.get("candidate_kind") not in {"exact_object", "ambiguous_group"}:
            raise ValueError("unknown candidate kind")
        if not all(isinstance(candidate.get(field), str) and candidate[field].strip()
                   for field in ("display_name", "craft", "node_id", "node_name")):
            raise ValueError("candidate public identity is incomplete")
        if candidate["candidate_kind"] == "exact_object":
            if not isinstance(candidate.get("ornament_id"), str) or not candidate["ornament_id"]:
                raise ValueError("exact candidate needs ornament_id")
            if candidate.get("selectable_for_exact_detail") is not True:
                raise ValueError("exact candidate must be selectable")
        else:
            members = candidate.get("member_ornament_ids")
            if not isinstance(members, list) or len(members) < 2:
                raise ValueError("ambiguous group needs multiple member ids")
            if candidate.get("selectable_for_exact_detail") is not False:
                raise ValueError("ambiguous group must remain unselectable")
    return {
        "schema_version": SCHEMA_VERSION,
        "request_kind": "ornament_story",
        "original_query": original_query,
        "subject_name": subject_name,
        "candidate_summaries": normalized,
        "requested_detail": requested_detail,
        "evidence_scope": evidence_scope,
        "expires_after_turns": 1,
    }


def load_pending_ornament_clarification(value: Any) -> dict[str, Any] | None:
    """Fail closed for malformed or expired persisted state."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return None
    try:
        return create_pending_ornament_clarification(
            original_query=str(value["original_query"]),
            subject_name=str(value["subject_name"]),
            candidates=value["candidate_summaries"],
            requested_detail=str(value["requested_detail"]),
            evidence_scope=str(value["evidence_scope"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def clear_pending_ornament_clarification(_: Any = None) -> None:
    """Represent removal explicitly without storing an empty fact container."""
    return None


def resolve_pending_ornament_choice(
    user_query: str,
    pending_value: Any,
) -> dict[str, Any]:
    """Resolve a single deterministic category choice, never a member by rank."""
    pending = load_pending_ornament_clarification(pending_value)
    if pending is None:
        return {"status": "missing"}
    text = user_query.strip()
    candidates = pending["candidate_summaries"]
    matches: list[dict[str, Any]] = []
    if text in {str(candidate["choice_index"]) for candidate in candidates}:
        matches = [candidate for candidate in candidates if text == str(candidate["choice_index"])]
    elif any(token in text for token in ("第一个", "第一", "1号")):
        matches = [candidate for candidate in candidates if candidate["choice_index"] == 1]
    elif any(token in text for token in ("第二个", "第二", "2号")):
        matches = [candidate for candidate in candidates if candidate["choice_index"] == 2]
    else:
        crafts = [candidate for candidate in candidates if candidate["craft"] in text]
        points = [candidate for candidate in candidates if candidate["node_name"] in text]
        matches = crafts or points
    if len(matches) != 1:
        return {"status": "unresolved", "pending": pending}
    candidate = matches[0]
    if candidate["candidate_kind"] == "ambiguous_group":
        return {"status": "data_ambiguity", "candidate": candidate, "pending": pending}
    return {"status": "selected", "candidate": candidate, "pending": pending}
