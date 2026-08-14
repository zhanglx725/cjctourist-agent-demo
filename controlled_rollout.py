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
NARRATION_COMPOSITION = "narration_composition"
ROLE_NARRATION = "role_narration"
ROLE_QA = "role_qa"
PRESENTATION_CONTENT_PLAN = "presentation_content_plan"

ROLE_ACTIVE_ENABLED_ENV = "ROLE_ACTIVE_ENABLED"
ROLE_ACTIVE_STYLES_ENV = "ROLE_ACTIVE_STYLES"
ROLE_ACTIVE_SCENES_ENV = "ROLE_ACTIVE_SCENES"
STOP_GUIDANCE_ACTIVE_STYLE_BATCHES = (
 ("neutral", "child", "family", "student_research", "professional", "listen_only", "mixed_group"),
 ("dominant_ceo", "cute_junior", "ancient_scholar", "warm_sister", "bestie_chat", "buddy_guide"),
 ("exploration_game", "photo_guide", "hostel_scholar", "xiguan_young_master", "cantonese_storyteller"),
)
STOP_GUIDANCE_ACTIVE_STYLES = frozenset(
 style_id for batch in STOP_GUIDANCE_ACTIVE_STYLE_BATCHES for style_id in batch
)
COMPETITION_ROLE_ACTIVE_PAIRS = frozenset({
 *{(style_id, "route_planning") for style_id in STOP_GUIDANCE_ACTIVE_STYLES},
 *{(style_id, "route_opening") for style_id in STOP_GUIDANCE_ACTIVE_STYLES},
 *{(style_id, "stop_guidance") for style_id in STOP_GUIDANCE_ACTIVE_STYLES},
})


@dataclass(frozen=True)
class ReadOnlyRollout:
 mode: RolloutMode=RolloutMode.OFF
 enabled_capabilities: frozenset[str]=frozenset({CONTROLLED_KNOWLEDGE})
 def enabled(self, capability: str)->bool: return self.mode is RolloutMode.READ_ONLY_ACTIVE and capability in self.enabled_capabilities
 def observes(self, capability: str)->bool: return self.mode is RolloutMode.SHADOW and capability in self.enabled_capabilities


@dataclass(frozen=True)
class CompetitionRoleActivePolicy:
 """Fail-closed competition whitelist layered over the existing rollout."""

 enabled: bool = False
 styles: frozenset[str] = frozenset()
 scenes: frozenset[str] = frozenset()

 def allows(self, style_id: str, scene_kind: str) -> bool:
  return bool(
   self.enabled
   and style_id in self.styles
   and scene_kind in self.scenes
   and (style_id, scene_kind) in COMPETITION_ROLE_ACTIVE_PAIRS
  )


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


def competition_role_active_from_environment(
 environ: Mapping[str, str] | None = None,
) -> CompetitionRoleActivePolicy:
 """Read the competition Active allowlist; invalid or incomplete means off."""

 values = os.environ if environ is None else environ
 enabled = values.get(ROLE_ACTIVE_ENABLED_ENV, "").strip().lower() == "true"
 styles = frozenset(
  item.strip() for item in values.get(ROLE_ACTIVE_STYLES_ENV, "").split(",")
  if item.strip()
 )
 scenes = frozenset(
  item.strip() for item in values.get(ROLE_ACTIVE_SCENES_ENV, "").split(",")
  if item.strip()
 )
 if not enabled or not styles or not scenes:
  return CompetitionRoleActivePolicy()
 return CompetitionRoleActivePolicy(True, styles, scenes)


def competition_role_active_allowed(
 style_id: str,
 scene_kind: str,
 environ: Mapping[str, str] | None = None,
) -> bool:
 """Require both the mature rollout gate and the competition pair gate."""

 rollout = rollout_from_environment(environ)
 return bool(
  rollout.enabled(ROLE_NARRATION)
  and competition_role_active_from_environment(environ).allows(
   style_id, scene_kind
  )
 )


def evaluation_record(thread_id: str, legacy: Mapping[str, Any], candidate: Mapping[str, Any] | None, *, mode: RolloutMode, outcome: str)->dict[str, Any]:
 """Thread-scoped comparison data; never visitor-visible state."""
 return {"thread_id":thread_id,"mode":mode.value,"outcome":outcome,"legacy_status":legacy.get("status"),"candidate_status":candidate.get("status") if candidate else None,"same_message":bool(candidate and legacy.get("message")==candidate.get("message"))}
