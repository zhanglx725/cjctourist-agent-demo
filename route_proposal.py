"""CA-09 proposal-only wrapper around reviewed route planning."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from route_planner import RoutePlan, RoutePlanningError, plan_template
from route_selection import RouteSelection

@dataclass(frozen=True)
class RouteProposal:
    proposal: dict[str, object] | None
    message: str
    requires_confirmation: bool
    status: str


@dataclass(frozen=True)
class RouteProposalAudit:
    """A proposal-shaped audit envelope for an already selected route only."""

    proposal: dict[str, object] | None
    validation_status: str
    rejected_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal": dict(self.proposal) if self.proposal is not None else None,
            "validation_status": self.validation_status,
            "rejected_reason": self.rejected_reason,
        }


def wrap_route_selection_for_shadow(
    selection: RouteSelection,
    *,
    input_snapshot: Mapping[str, object],
    route_data_version: Mapping[str, str],
) -> RouteProposalAudit:
    """Wrap one existing deterministic selection without planning or mutation."""
    if not isinstance(selection, RouteSelection):
        return RouteProposalAudit(None, "rejected", "selection_schema_invalid")
    if selection.route_strategy not in {"anchor", "dynamic"}:
        return RouteProposalAudit(None, "rejected", "route_strategy_unapproved")
    if not selection.route_id or not selection.guide_stop_ids:
        return RouteProposalAudit(None, "rejected", "selected_route_incomplete")
    if selection.estimated_total_seconds <= 0:
        return RouteProposalAudit(None, "rejected", "route_total_invalid")
    budget_seconds = int(selection.requested_minutes) * 60
    if selection.estimated_total_seconds > budget_seconds:
        return RouteProposalAudit(None, "rejected", "strict_budget_exceeded")
    if not isinstance(selection.selection_reason, dict):
        return RouteProposalAudit(None, "rejected", "selection_reason_invalid")
    proposal: dict[str, object] = {
        "route_strategy": selection.route_strategy,
        "selected_route_id": selection.route_id,
        "guide_stop_ids": list(selection.guide_stop_ids),
        "estimated_total_seconds": selection.estimated_total_seconds,
        "budget_breakdown": {
            "requested_minutes": selection.requested_minutes,
            "budget_seconds": budget_seconds,
            "explanation_seconds": selection.estimated_explanation_seconds,
            "observation_seconds": selection.estimated_observation_seconds,
            "interaction_seconds": selection.estimated_interaction_seconds,
            "exit_return_seconds": selection.estimated_exit_return_seconds,
        },
        "walking_seconds": selection.estimated_walk_seconds,
        "selection_reason": dict(selection.selection_reason),
        "route_data_version": dict(route_data_version),
        "input_snapshot": dict(input_snapshot),
    }
    return RouteProposalAudit(proposal, "accepted")

def propose_reviewed_route(route_id: str, *, planner: Callable[[str], RoutePlan] = plan_template) -> RouteProposal:
    """Produce an audited candidate only; never initializes or replaces a tour."""
    try: plan = planner(route_id)
    except (RoutePlanningError, OSError, ValueError):
        return RouteProposal(None, "当前无法根据现有路线生成可确认的参观方案。", False, "unavailable")
    if not plan.within_time_budget or not plan.stop_ids or not plan.exit_node_id:
        return RouteProposal(None, "当前路线不满足时间或空间条件，因此不会提交。", False, "rejected")
    return RouteProposal(plan.to_dict(), "我已整理一条待您确认的参观路线；确认前不会改变当前导览进度。", True, "proposed")
