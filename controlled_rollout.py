"""P2-05 configuration and per-thread audit contract for read-only rollout."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
import os
from typing import Any, Mapping


class RolloutMode(StrEnum):
 OFF="off"; SHADOW="shadow"; READ_ONLY_ACTIVE="read_only_active"


CONTROLLED_KNOWLEDGE = "controlled_knowledge"
ATOMIC_READ_PLAN = "atomic_read_plan"
ROUTE_PROPOSAL = "route_proposal"
REPLAN_PROPOSAL = "replan_proposal"
STATE_TRANSITION = "state_transition"


@dataclass(frozen=True)
class ReadOnlyRollout:
 mode: RolloutMode=RolloutMode.OFF
 enabled_capabilities: frozenset[str]=frozenset({CONTROLLED_KNOWLEDGE})
 def enabled(self, capability: str)->bool: return self.mode is RolloutMode.READ_ONLY_ACTIVE and capability in self.enabled_capabilities
 def observes(self, capability: str)->bool: return self.mode is RolloutMode.SHADOW and capability in self.enabled_capabilities


def rollout_from_environment(environ: Mapping[str, str] | None = None) -> ReadOnlyRollout:
 """Read a fail-closed, per-capability rollout configuration.

 Invalid values and an empty capability set both disable the new chain.  The
 function reads on demand so Studio and CLI observe the same process config.
 """
 values = os.environ if environ is None else environ
 try:
  mode = RolloutMode(values.get("CJC_READ_ONLY_ROLLOUT_MODE", RolloutMode.OFF))
 except ValueError:
  return ReadOnlyRollout()
 raw = values.get("CJC_READ_ONLY_ROLLOUT_CAPABILITIES", CONTROLLED_KNOWLEDGE)
 capabilities = frozenset(item.strip() for item in raw.split(",") if item.strip())
 return ReadOnlyRollout(mode, capabilities)


def evaluation_record(thread_id: str, legacy: Mapping[str, Any], candidate: Mapping[str, Any] | None, *, mode: RolloutMode, outcome: str)->dict[str, Any]:
 """Thread-scoped comparison data; never visitor-visible state."""
 return {"thread_id":thread_id,"mode":mode.value,"outcome":outcome,"legacy_status":legacy.get("status"),"candidate_status":candidate.get("status") if candidate else None,"same_message":bool(candidate and legacy.get("message")==candidate.get("message"))}
