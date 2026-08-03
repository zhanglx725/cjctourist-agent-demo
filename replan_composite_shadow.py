"""Pure audit records for legacy P1-11 replan composite operations."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


def _formal_snapshot(state: Mapping[str, Any] | None) -> dict[str, Any]:
    source = state or {}
    return {
        "selected_route_id": source.get("selected_route_id"),
        "current_stop_id": source.get("current_stop_id"),
        "visited_stop_ids": list(source.get("visited_stop_ids") or ()),
        "skipped_stop_ids": list(source.get("skipped_stop_ids") or ()),
        "remaining_stop_ids": list(source.get("remaining_stop_ids") or ()),
    }


def audit_replan_composite_operation(
    *,
    operation_kind: str,
    legacy_event_sequence: Sequence[str],
    tour_before: Mapping[str, Any] | None,
    tour_after: Mapping[str, Any] | None,
    interaction_before: Mapping[str, Any] | None,
    interaction_after: Mapping[str, Any] | None,
    proposal_before: Mapping[str, Any] | None,
    proposal_after: Mapping[str, Any] | None,
    time_confirmation_before: Mapping[str, Any] | None,
    time_confirmation_after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare legacy P1-11 inputs and outputs without executing anything."""
    before = _formal_snapshot(tour_before)
    after = _formal_snapshot(tour_after)
    proposal_before_copy = deepcopy(dict(proposal_before)) if proposal_before else None
    proposal_after_copy = deepcopy(dict(proposal_after)) if proposal_after else None
    sequence = list(legacy_event_sequence)
    route_changed = before["selected_route_id"] != after["selected_route_id"]
    progress_changed = (
        before["visited_stop_ids"] != after["visited_stop_ids"]
        or before["skipped_stop_ids"] != after["skipped_stop_ids"]
    )
    pending_before = (interaction_before or {}).get("pending_stop_id")
    pending_after = (interaction_after or {}).get("pending_stop_id")

    expected = False
    reason_codes: list[str] = []
    if operation_kind == "prepare_replan":
        expected = (
            not route_changed
            and not progress_changed
            and proposal_after_copy is None
            and isinstance(time_confirmation_after, Mapping)
        )
        reason_codes.append("replan_time_confirmation_prepared" if expected else "prepare_contract_mismatch")
    elif operation_kind == "prepare_replan_candidate":
        expected = (
            not route_changed
            and not progress_changed
            and proposal_after_copy is not None
            and proposal_after_copy.get("status") == "awaiting_route_confirmation"
        )
        reason_codes.append("proposal_prepared" if expected else "proposal_prepare_contract_mismatch")
    elif operation_kind == "confirm_replan":
        expected = (
            sequence == ["apply_replan_proposal"]
            and proposal_before_copy is not None
            and proposal_after_copy is None
            and after["selected_route_id"] == proposal_before_copy.get("route_id")
        )
        reason_codes.append("proposal_applied" if expected else "confirm_contract_mismatch")
    elif operation_kind == "confirm_replan_and_next":
        expected = (
            sequence == ["apply_replan_proposal", "next_stop"]
            and proposal_before_copy is not None
            and proposal_after_copy is None
            and after["selected_route_id"] == proposal_before_copy.get("route_id")
            and pending_after in after["remaining_stop_ids"]
        )
        reason_codes.append("proposal_applied_then_next_stop" if expected else "composite_contract_mismatch")
    elif operation_kind == "cancel_replan":
        expected = (
            sequence == []
            and proposal_after_copy is None
            and time_confirmation_after is None
            and not route_changed
            and not progress_changed
        )
        reason_codes.append("pending_action_cleared" if expected else "cancel_contract_mismatch")
    elif operation_kind == "confirm_replan_without_pending":
        expected = (
            sequence == []
            and proposal_before_copy is None
            and proposal_after_copy is None
            and not route_changed
            and not progress_changed
        )
        reason_codes.append("no_pending_proposal" if expected else "missing_proposal_contract_mismatch")
    else:
        reason_codes.append("unsupported_operation")

    return {
        "operation_kind": operation_kind,
        "legacy_event_sequence": sequence,
        "proposal_before_status": proposal_before_copy.get("status") if proposal_before_copy else None,
        "proposal_after_status": proposal_after_copy.get("status") if proposal_after_copy else None,
        "formal_route_changed": route_changed,
        "visited_or_skipped_changed": progress_changed,
        "pending_stop_before_after": {"before": pending_before, "after": pending_after},
        "matches_expected_contract": expected,
        "reason_codes": reason_codes,
    }
