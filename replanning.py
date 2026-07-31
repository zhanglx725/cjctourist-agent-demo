"""Deterministic replanning for skip, time changes, and P1-11 proposals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from route_planner import RemainingRoutePlan, plan_from_current_position
from tour_state import apply_replanned_route, skip_stop


@dataclass(frozen=True)
class ReplanResult:
    tour_state: dict[str, Any]
    plan: RemainingRoutePlan
    reason: str


@dataclass(frozen=True)
class RemainingRouteProposal:
    """A non-mutating proposal whose origin is an audited physical snapshot."""

    schema_version: str
    status: str
    pending_action_kind: str
    origin_node_id: str
    origin_source: str
    physical_node_snapshot: str
    route_id: str
    remaining_minutes: int
    stop_ids: tuple[str, ...]
    dropped_stop_ids: tuple[str, ...]
    full_path_node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_total_seconds: int | None
    allowed_total_seconds: int
    within_time_budget: bool | None
    visited_stop_ids_snapshot: tuple[str, ...]
    skipped_stop_ids_snapshot: tuple[str, ...]
    current_is_formal_unconfirmed_stop: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Stable, UI-facing audit aliases.  ``stop_ids`` are formal guide
        # stops; the complete spatial path separately proves the route origin.
        data["guide_stop_ids"] = list(self.stop_ids)
        data["path_node_ids"] = list(self.full_path_node_ids)
        segments: list[dict[str, str]] = []
        previous = self.origin_node_id
        for node_id in self.stop_ids:
            if node_id != previous:
                segments.append({"from_node_id": previous, "to_node_id": node_id})
            previous = node_id
        data["route_segments"] = segments
        return data


@dataclass(frozen=True)
class RemainingTimeConfirmation:
    """A non-mutating request for the visitor's actual remaining time.

    The route's initial budget is intentionally not copied into this object as
    a presumed live value.  A deviation establishes location, not elapsed time.
    """

    schema_version: str
    status: str
    pending_action_kind: str
    origin_node_id: str
    origin_source: str
    physical_node_snapshot: str
    route_id_snapshot: str
    visited_stop_ids_snapshot: tuple[str, ...]
    skipped_stop_ids_snapshot: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def prepare_remaining_time_confirmation(
    state: dict[str, Any],
    *,
    origin_node_id: str,
    origin_source: str,
) -> RemainingTimeConfirmation:
    """Prepare a time question after a self-arrival without inferring minutes."""
    current = state.get("current_stop_id")
    if (
        not current
        or current != origin_node_id
        or state.get("route_status") == "completed"
        or not state.get("selected_route_id")
    ):
        raise ValueError("只能从活跃路线中的当前确认位置请求后续时间。")
    return RemainingTimeConfirmation(
        schema_version="v1",
        status="replan_time_confirmation",
        pending_action_kind="replan_time_confirmation",
        origin_node_id=current,
        origin_source=origin_source,
        physical_node_snapshot=current,
        route_id_snapshot=str(state["selected_route_id"]),
        visited_stop_ids_snapshot=tuple(state.get("visited_stop_ids", [])),
        skipped_stop_ids_snapshot=tuple(state.get("skipped_stop_ids", [])),
    )


def prepare_remaining_route_proposal(
    state: dict[str, Any],
    *,
    origin_node_id: str,
    origin_source: str,
    remaining_minutes: int | None = None,
) -> RemainingRouteProposal:
    """Build a preview from the current physical node without changing a route.

    ``origin_node_id`` must equal ``TourState.current_stop_id``.  It is kept
    only as a proposal freshness snapshot, never as a second location fact.
    """
    current = state.get("current_stop_id")
    if not current or current != origin_node_id:
        raise ValueError("重规划候选必须从当前确认的位置创建。")
    remaining_ids = list(state.get("remaining_stop_ids", []))
    route_order = list(state.get("route_stop_ids", []))
    current_is_formal_unconfirmed_stop = current in remaining_ids
    if current in route_order:
        future = set(route_order[route_order.index(current) + 1 :])
        remaining_ids = [node_id for node_id in remaining_ids if node_id in future]
    budget_minutes = int(state["remaining_minutes"]) if remaining_minutes is None else remaining_minutes
    if not isinstance(budget_minutes, int) or budget_minutes <= 0:
        raise ValueError("请提供大于 0 的明确剩余分钟数。")
    plan = plan_from_current_position(
        current_stop_id=current,
        remaining_minutes=budget_minutes,
        excluded_stop_ids=[*state.get("visited_stop_ids", []), *state.get("skipped_stop_ids", [])],
        preferred_route_id=state["selected_route_id"].removesuffix("_replanned"),
        candidate_stop_ids=remaining_ids,
    )
    proposed_stop_ids = (
        (current, *plan.stop_ids)
        if current_is_formal_unconfirmed_stop
        else tuple(plan.stop_ids)
    )
    if not proposed_stop_ids or plan.within_time_budget is not True:
        raise ValueError("当前时间预算内没有可安全应用的后续路线候选。")
    if not plan.full_path_node_ids or plan.full_path_node_ids[0] != current:
        raise ValueError("候选空间路径未从当前确认的位置出发。")
    return RemainingRouteProposal(
        schema_version="v1",
        status="awaiting_route_confirmation",
        pending_action_kind="replan_route_confirmation",
        origin_node_id=current,
        origin_source=origin_source,
        physical_node_snapshot=current,
        route_id=plan.route_id,
        remaining_minutes=budget_minutes,
        stop_ids=tuple(proposed_stop_ids),
        dropped_stop_ids=tuple(plan.dropped_stop_ids),
        full_path_node_ids=tuple(plan.full_path_node_ids),
        edge_ids=tuple(plan.edge_ids),
        estimated_total_seconds=plan.estimated_total_seconds,
        allowed_total_seconds=plan.allowed_total_seconds,
        within_time_budget=plan.within_time_budget,
        visited_stop_ids_snapshot=tuple(state.get("visited_stop_ids", [])),
        skipped_stop_ids_snapshot=tuple(state.get("skipped_stop_ids", [])),
        current_is_formal_unconfirmed_stop=current_is_formal_unconfirmed_stop,
    )


def replan_remaining_time(state: dict[str, Any], remaining_minutes: int) -> ReplanResult:
    """Replan only the unvisited, unskipped remainder from the real current node."""
    remaining_ids = list(state.get("remaining_stop_ids", []))
    current = state.get("current_stop_id")
    current_is_unconfirmed_stop = current in remaining_ids
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
        # A1 keeps an arrived-but-unconfirmed stop in remaining state.  It is
        # not a new planner candidate and therefore cannot be duplicated.
        preserve_current_stop=current_is_unconfirmed_stop,
    )
    return ReplanResult(updated, plan, "remaining_time_changed")


def replan_after_skip(state: dict[str, Any], node_id: str | None = None) -> ReplanResult:
    """Skip one remaining stop, then rebuild the walkable remaining route."""
    skipped = skip_stop(state, node_id)
    result = replan_remaining_time(skipped, int(skipped["remaining_minutes"]))
    return ReplanResult(result.tour_state, result.plan, "stop_skipped")
