"""CA-10 confirmation-only adapter for frozen replanning previews."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from replanning import RemainingRouteProposal, prepare_remaining_route_proposal

@dataclass(frozen=True)
class ReplanProposalResult:
 proposal: dict[str, Any] | None
 status: str
 message: str

@dataclass(frozen=True)
class ReplanProposalAudit:
 proposal: dict[str, Any] | None
 validation_status: str
 rejected_reason: str | None=None
 def to_dict(self)->dict[str, Any]:
  return {"proposal":deepcopy(self.proposal) if self.proposal is not None else None,"validation_status":self.validation_status,"rejected_reason":self.rejected_reason}

def wrap_existing_replan_proposal_for_shadow(proposal: Mapping[str, Any] | None, tour_state: Mapping[str, Any] | None) -> ReplanProposalAudit:
 """Validate and copy one legacy P1-11 preview; never recalculate or apply it."""
 if not isinstance(proposal, Mapping): return ReplanProposalAudit(None,"rejected","legacy_proposal_absent")
 if not isinstance(tour_state, Mapping): return ReplanProposalAudit(None,"rejected","active_route_absent")
 required=("origin_node_id","physical_node_snapshot","route_id","remaining_minutes","guide_stop_ids","visited_stop_ids_snapshot","skipped_stop_ids_snapshot","status","pending_action_kind")
 if any(key not in proposal for key in required): return ReplanProposalAudit(None,"rejected","proposal_schema_invalid")
 origin=proposal.get("origin_node_id")
 if proposal.get("status")!="awaiting_route_confirmation" or proposal.get("pending_action_kind")!="replan_route_confirmation": return ReplanProposalAudit(None,"rejected","proposal_not_pending")
 if not isinstance(origin,str) or proposal.get("physical_node_snapshot")!=origin or tour_state.get("current_stop_id")!=origin: return ReplanProposalAudit(None,"rejected","origin_snapshot_stale")
 if list(proposal.get("visited_stop_ids_snapshot",[]))!=list(tour_state.get("visited_stop_ids",[])) or list(proposal.get("skipped_stop_ids_snapshot",[]))!=list(tour_state.get("skipped_stop_ids",[])): return ReplanProposalAudit(None,"rejected","route_snapshot_stale")
 if not isinstance(proposal.get("remaining_minutes"),int) or proposal["remaining_minutes"]<=0: return ReplanProposalAudit(None,"rejected","remaining_minutes_invalid")
 return ReplanProposalAudit(deepcopy(dict(proposal)),"accepted")

def propose_remaining_route(state: Mapping[str, Any], *, origin_node_id: str, origin_source: str, remaining_minutes: int | None = None, preparer: Callable[..., RemainingRouteProposal] = prepare_remaining_route_proposal) -> ReplanProposalResult:
 """Create no proposal if snapshot/budget validation fails; never apply it."""
 try: proposal=preparer(deepcopy(dict(state)),origin_node_id=origin_node_id,origin_source=origin_source,remaining_minutes=remaining_minutes)
 except (ValueError, KeyError, OSError): return ReplanProposalResult(None,"unavailable","当前无法生成可确认的后续路线方案。")
 return ReplanProposalResult(proposal.to_dict(),"awaiting_confirmation","我已整理后续路线候选；请确认后再调整导览进度。")
