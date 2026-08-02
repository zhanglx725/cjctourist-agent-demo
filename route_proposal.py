"""CA-09 proposal-only wrapper around reviewed route planning."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from route_planner import RoutePlan, RoutePlanningError, plan_template

@dataclass(frozen=True)
class RouteProposal:
    proposal: dict[str, object] | None
    message: str
    requires_confirmation: bool
    status: str

def propose_reviewed_route(route_id: str, *, planner: Callable[[str], RoutePlan] = plan_template) -> RouteProposal:
    """Produce an audited candidate only; never initializes or replaces a tour."""
    try: plan = planner(route_id)
    except (RoutePlanningError, OSError, ValueError):
        return RouteProposal(None, "当前无法根据已审核路线生成可确认的参观方案。", False, "unavailable")
    if not plan.within_time_budget or not plan.stop_ids or not plan.exit_node_id:
        return RouteProposal(None, "当前路线候选未通过时间或空间审核，因此不会提交。", False, "rejected")
    return RouteProposal(plan.to_dict(), "我已整理一条待您确认的参观路线；确认前不会改变当前导览进度。", True, "proposed")
