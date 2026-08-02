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

def propose_remaining_route(state: Mapping[str, Any], *, origin_node_id: str, origin_source: str, remaining_minutes: int | None = None, preparer: Callable[..., RemainingRouteProposal] = prepare_remaining_route_proposal) -> ReplanProposalResult:
 """Create no proposal if snapshot/budget validation fails; never apply it."""
 try: proposal=preparer(deepcopy(dict(state)),origin_node_id=origin_node_id,origin_source=origin_source,remaining_minutes=remaining_minutes)
 except (ValueError, KeyError, OSError): return ReplanProposalResult(None,"unavailable","当前无法生成可确认的后续路线方案。")
 return ReplanProposalResult(proposal.to_dict(),"awaiting_confirmation","我已整理后续路线候选；请确认后再调整导览进度。")
