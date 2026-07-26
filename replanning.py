"""Limited deterministic replanning for skip and remaining-time changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from route_planner import RemainingRoutePlan, plan_from_current_position
from tour_state import apply_replanned_route, skip_stop


@dataclass(frozen=True)
class ReplanResult:
    tour_state: dict[str, Any]
    plan: RemainingRoutePlan
    reason: str


def replan_remaining_time(state: dict[str, Any], remaining_minutes: int) -> ReplanResult:
    """Replan only the unvisited, unskipped remainder from the real current node."""
    remaining_ids = list(state.get("remaining_stop_ids", []))
    current = state.get("current_stop_id")
    route_order = list(state.get("route_stop_ids", []))
    # If the visitor is already at a formal stop, do not send them backward to
    # an earlier unvisited stop.  Continue with the original route suffix.
    if current in route_order:
        future_ids = set(route_order[route_order.index(current) + 1 :])
        remaining_ids = [node_id for node_id in remaining_ids if node_id in future_ids]
    plan = plan_from_current_position(
        current_stop_id=current,
        remaining_minutes=remaining_minutes,
        excluded_stop_ids=[*state.get("visited_stop_ids", []), *state.get("skipped_stop_ids", [])],
        preferred_route_id=state["selected_route_id"].removesuffix("_replanned"),
        candidate_stop_ids=remaining_ids,
    )
    updated = apply_replanned_route(
        state,
        list(plan.stop_ids),
        remaining_minutes,
        selected_route_id=plan.route_id,
    )
    return ReplanResult(updated, plan, "remaining_time_changed")


def replan_after_skip(state: dict[str, Any], node_id: str | None = None) -> ReplanResult:
    """Skip one remaining stop, then rebuild the walkable remaining route."""
    skipped = skip_stop(state, node_id)
    result = replan_remaining_time(skipped, int(skipped["remaining_minutes"]))
    return ReplanResult(result.tour_state, result.plan, "stop_skipped")
