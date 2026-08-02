"""P2-05 configuration and per-thread audit contract for read-only rollout."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
class RolloutMode(StrEnum): OFF="off"; SHADOW="shadow"; READ_ONLY_ACTIVE="read_only_active"
@dataclass(frozen=True)
class ReadOnlyRollout:
 mode: RolloutMode=RolloutMode.OFF
 enabled_capabilities: frozenset[str]=frozenset({"controlled_knowledge"})
 def enabled(self, capability: str)->bool: return self.mode is RolloutMode.READ_ONLY_ACTIVE and capability in self.enabled_capabilities
 def observes(self, capability: str)->bool: return self.mode is RolloutMode.SHADOW and capability in self.enabled_capabilities
def evaluation_record(thread_id: str, legacy: Mapping[str, Any], candidate: Mapping[str, Any] | None)->dict[str, Any]:
 """Thread-scoped comparison data; never visitor-visible state."""
 return {"thread_id":thread_id,"legacy_mode":legacy.get("mode"),"candidate_mode":candidate.get("mode") if candidate else None,"same_message":bool(candidate and legacy.get("message")==candidate.get("message"))}
