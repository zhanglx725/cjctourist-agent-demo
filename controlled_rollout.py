"""P2-05 configuration and per-thread audit contract for read-only rollout."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
import hashlib
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
PRODUCT_ROLE_ACTIVE_ENABLED_ENV = "PRODUCT_ROLE_ACTIVE_ENABLED"
PRODUCT_ROLE_ACTIVE_STYLES_ENV = "PRODUCT_ROLE_ACTIVE_STYLES"
PRODUCT_ROLE_ACTIVE_SCENES_ENV = "PRODUCT_ROLE_ACTIVE_SCENES"
PRODUCT_ROLE_ROLLOUT_PERCENTAGE_ENV = "PRODUCT_ROLE_ROLLOUT_PERCENTAGE"
PRODUCT_ROLE_KILL_SWITCH_ENV = "PRODUCT_ROLE_KILL_SWITCH"
PRODUCT_ROLE_VALIDATION_LEVEL_ENV = "PRODUCT_ROLE_VALIDATION_LEVEL"
PRODUCT_ROLE_FALLBACK_POLICY_ENV = "PRODUCT_ROLE_FALLBACK_POLICY"
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
PRODUCT_ROLE_SCENES = frozenset({
 "route_planning", "route_opening", "stop_guidance", "tour_qa",
 "qa_follow_up_detail", "navigation", "tour_closing", "replan_presentation",
})
PRODUCT_ROLE_ACTIVE_PAIRS = frozenset(
 (style_id, scene_kind)
 for style_id in STOP_GUIDANCE_ACTIVE_STYLES
 for scene_kind in PRODUCT_ROLE_SCENES
)


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


@dataclass(frozen=True)
class ProductStylePolicy:
 """One reviewed presentation style in a product capability policy."""

 style_id: str
 enabled: bool = True


@dataclass(frozen=True)
class ProductScenePolicy:
 """One scene and its allowed presentation styles."""

 scene_kind: str
 styles: tuple[ProductStylePolicy, ...] = ()
 enabled: bool = True

 def allows(self, style_id: str) -> bool:
  return bool(
   self.enabled
   and any(style.enabled and style.style_id == style_id for style in self.styles)
  )


@dataclass(frozen=True)
class ProductCapabilityPolicy:
 """Fail-closed product policy for one role-expression capability.

 Legacy ROLE_ACTIVE_* variables are accepted only when no PRODUCT_ROLE_*
 variable is present.  A partial product configuration never falls back to
 the legacy configuration because that could accidentally broaden access.
 """

 enabled: bool = False
 styles: frozenset[str] = frozenset()
 scenes: frozenset[str] = frozenset()
 rollout_percentage: int = 0
 validation_level: str = "strict"
 fallback_policy: str = "legacy"
 kill_switch: bool = False
 source: str = "disabled"
 reason_code: str | None = None

 @property
 def scene_policies(self) -> tuple[ProductScenePolicy, ...]:
  return tuple(
   ProductScenePolicy(
    scene_kind=scene_kind,
    styles=tuple(ProductStylePolicy(style_id) for style_id in sorted(self.styles)),
   )
   for scene_kind in sorted(self.scenes)
  )

 def allows(
  self, style_id: str, scene_kind: str, *, thread_id: str | None = None,
 ) -> bool:
  if (
   not self.enabled or self.kill_switch
   or self.validation_level != "strict"
   or self.fallback_policy != "legacy"
   or not any(
    scene.scene_kind == scene_kind and scene.allows(style_id)
    for scene in self.scene_policies
   )
   or (style_id, scene_kind) not in PRODUCT_ROLE_ACTIVE_PAIRS
  ):
   return False
  if self.rollout_percentage >= 100:
   return True
  if self.rollout_percentage <= 0 or not thread_id:
   return False
  bucket = int.from_bytes(
   hashlib.sha256(
    f"{thread_id}:{style_id}:{scene_kind}".encode("utf-8")
   ).digest()[:4], "big",
  ) % 10000
  return bucket < self.rollout_percentage * 100

 def to_audit(self) -> dict[str, Any]:
  return {
   "enabled": self.enabled,
   "styles": sorted(self.styles),
   "scenes": sorted(self.scenes),
   "rollout_percentage": self.rollout_percentage,
   "validation_level": self.validation_level,
   "fallback_policy": self.fallback_policy,
   "kill_switch": self.kill_switch,
   "source": self.source,
   "reason_code": self.reason_code,
  }


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


def _strict_bool(value: str | None) -> bool | None:
 normalized = str(value or "").strip().lower()
 if normalized == "true":
  return True
 if normalized == "false":
  return False
 return None


def product_capability_policy_from_environment(
 environ: Mapping[str, str] | None = None,
) -> ProductCapabilityPolicy:
 """Read the product role policy, with strict legacy compatibility."""

 values = os.environ if environ is None else environ
 product_keys = {
  PRODUCT_ROLE_ACTIVE_ENABLED_ENV, PRODUCT_ROLE_ACTIVE_STYLES_ENV,
  PRODUCT_ROLE_ACTIVE_SCENES_ENV, PRODUCT_ROLE_ROLLOUT_PERCENTAGE_ENV,
  PRODUCT_ROLE_KILL_SWITCH_ENV, PRODUCT_ROLE_VALIDATION_LEVEL_ENV,
  PRODUCT_ROLE_FALLBACK_POLICY_ENV,
 }
 product_configured = any(key in values for key in product_keys)
 if not product_configured:
  legacy = competition_role_active_from_environment(values)
  return ProductCapabilityPolicy(
   enabled=legacy.enabled,
   styles=legacy.styles,
   scenes=legacy.scenes,
   rollout_percentage=100 if legacy.enabled else 0,
   source="legacy_compatibility" if legacy.enabled else "disabled",
   reason_code=None if legacy.enabled else "legacy_policy_disabled",
  )

 required = {
  PRODUCT_ROLE_ACTIVE_ENABLED_ENV, PRODUCT_ROLE_ACTIVE_STYLES_ENV,
  PRODUCT_ROLE_ACTIVE_SCENES_ENV, PRODUCT_ROLE_ROLLOUT_PERCENTAGE_ENV,
 }
 if any(key not in values for key in required):
  return ProductCapabilityPolicy(
   source="product", reason_code="incomplete_product_policy",
  )
 enabled = _strict_bool(values.get(PRODUCT_ROLE_ACTIVE_ENABLED_ENV))
 kill_switch = _strict_bool(values.get(PRODUCT_ROLE_KILL_SWITCH_ENV, "false"))
 if enabled is None or kill_switch is None:
  return ProductCapabilityPolicy(
   source="product", reason_code="invalid_product_policy_boolean",
  )
 styles = frozenset(
  item.strip() for item in values[PRODUCT_ROLE_ACTIVE_STYLES_ENV].split(",")
  if item.strip()
 )
 scenes = frozenset(
  item.strip() for item in values[PRODUCT_ROLE_ACTIVE_SCENES_ENV].split(",")
  if item.strip()
 )
 try:
  percentage = int(values[PRODUCT_ROLE_ROLLOUT_PERCENTAGE_ENV])
 except (TypeError, ValueError):
  return ProductCapabilityPolicy(
   source="product", reason_code="invalid_rollout_percentage",
  )
 validation_level = values.get(
  PRODUCT_ROLE_VALIDATION_LEVEL_ENV, "strict",
 ).strip()
 fallback_policy = values.get(
  PRODUCT_ROLE_FALLBACK_POLICY_ENV, "legacy",
 ).strip()
 if (
  not styles or not scenes or percentage < 0 or percentage > 100
  or validation_level != "strict" or fallback_policy != "legacy"
 ):
  return ProductCapabilityPolicy(
   source="product", reason_code="invalid_product_policy_values",
  )
 unknown_styles = styles - STOP_GUIDANCE_ACTIVE_STYLES
 if unknown_styles or scenes - PRODUCT_ROLE_SCENES:
  return ProductCapabilityPolicy(
   source="product", reason_code="unknown_product_policy_target",
  )
 return ProductCapabilityPolicy(
  enabled=enabled, styles=styles, scenes=scenes,
  rollout_percentage=percentage, validation_level=validation_level,
  fallback_policy=fallback_policy, kill_switch=kill_switch,
  source="product", reason_code=None if enabled else "product_policy_disabled",
 )


def product_role_active_allowed(
 style_id: str,
 scene_kind: str,
 environ: Mapping[str, str] | None = None,
 *,
 thread_id: str | None = None,
) -> bool:
 """Require mature rollout and the fail-closed product capability policy."""

 rollout = rollout_from_environment(environ)
 return bool(
  rollout.enabled(ROLE_NARRATION)
  and product_capability_policy_from_environment(environ).allows(
   style_id, scene_kind, thread_id=thread_id,
  )
 )


def evaluation_record(thread_id: str, legacy: Mapping[str, Any], candidate: Mapping[str, Any] | None, *, mode: RolloutMode, outcome: str)->dict[str, Any]:
 """Thread-scoped comparison data; never visitor-visible state."""
 return {"thread_id":thread_id,"mode":mode.value,"outcome":outcome,"legacy_status":legacy.get("status"),"candidate_status":candidate.get("status") if candidate else None,"same_message":bool(candidate and legacy.get("message")==candidate.get("message"))}
