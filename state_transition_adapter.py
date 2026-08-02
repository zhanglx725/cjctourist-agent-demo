"""CA-11 sole adapter for explicitly confirmed frozen tour events."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from tour_interaction import EVENTS, handle_tour_event
@dataclass(frozen=True)
class ConfirmedEvent:
 event: str
 payload: dict[str, Any]
 confirmed: bool
@dataclass(frozen=True)
class TransitionResult:
 applied: bool
 result: dict[str, Any] | None
 reason: str
def apply_confirmed_event(request: ConfirmedEvent, tour_state: Mapping[str, Any] | None, interaction_state: Mapping[str, Any] | None, *, handler: Callable[..., dict[str, Any]] = handle_tour_event) -> TransitionResult:
 if not request.confirmed: return TransitionResult(False,None,"confirmation_required")
 if request.event not in EVENTS: return TransitionResult(False,None,"invalid_event")
 try: result=handler(deepcopy(dict(tour_state)) if tour_state else None,deepcopy(dict(interaction_state)) if interaction_state else None,request.event,**deepcopy(request.payload))
 except Exception: return TransitionResult(False,None,"transition_unavailable")
 return TransitionResult(bool(result.get("ok")),result,"applied" if result.get("ok") else str(result.get("code") or "transition_rejected"))
