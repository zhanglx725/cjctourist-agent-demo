"""CA-05 non-executing planner observation for the future controlled graph.

This module is deliberately not imported by ``agent_graph``.  In its default
``off`` mode it makes no model call.  In ``shadow`` mode it observes one
validated candidate alongside a legacy outcome; it never selects a tool,
changes state, or produces a visitor response.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Any, Callable, Mapping

from agent_decision import DecisionValidation, validate_agent_decision


class ShadowMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"


@dataclass(frozen=True)
class ShadowPlannerConfig:
    mode: ShadowMode = ShadowMode.OFF
    timeout_ms: int = 1_500
    max_candidates_per_turn: int = 1

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0 or self.max_candidates_per_turn != 1:
            raise ValueError("shadow_planner_limits_rejected")


@dataclass(frozen=True)
class ShadowObservation:
    status: str
    legacy_outcome: dict[str, Any]
    candidate: dict[str, object] | None
    validation_code: str | None
    capability_matches_legacy: bool | None

    def audit_dict(self) -> dict[str, Any]:
        """Return audit-safe data only; raw model output and prompts are omitted."""
        return {
            "status": self.status,
            "legacy_outcome": dict(self.legacy_outcome),
            "candidate": dict(self.candidate) if self.candidate else None,
            "validation_code": self.validation_code,
            "capability_matches_legacy": self.capability_matches_legacy,
        }


def planner_prompt(user_text: str) -> str:
    """A fact-free, one-candidate protocol prompt for a later model adapter."""
    return (
        "你是只读影子规划器，不执行操作，不回答游客问题，不输出任何地点、对象、来源、卡片或路线 ID。"
        "只输出一个 JSON 对象，字段必须严格为 intent、sub_intents、requested_capability、target_text、"
        "evidence_span、confidence、requires_clarification、requires_confirmation、side_effect_level。"
        "target_text 与 evidence_span 必须完全相同且是用户原话连续片段。"
        "低置信度或无法确定时输出 clarification/read_only 候选。用户原话："
        f"{user_text}"
    )


def _decode(raw: object) -> Mapping[str, Any] | str:
    if isinstance(raw, Mapping):
        return raw
    if not isinstance(raw, str):
        return ""
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return decoded if isinstance(decoded, Mapping) else raw


def _match(validation: DecisionValidation, legacy_outcome: Mapping[str, Any]) -> bool | None:
    if not validation.accepted or validation.decision is None:
        return None
    legacy_capability = legacy_outcome.get("capability")
    return legacy_capability == validation.decision.requested_capability.value if isinstance(legacy_capability, str) else None


def observe_shadow_plan(
    user_text: str,
    legacy_outcome: Mapping[str, Any],
    invoke_model: Callable[[str], str | Mapping[str, Any]],
    *,
    config: ShadowPlannerConfig = ShadowPlannerConfig(),
) -> ShadowObservation:
    """Observe exactly one candidate without affecting the supplied legacy outcome."""
    legacy_copy = dict(legacy_outcome)
    if config.mode is ShadowMode.OFF:
        return ShadowObservation("off", legacy_copy, None, None, None)
    try:
        raw = invoke_model(planner_prompt(user_text))
    except Exception:
        return ShadowObservation("model_unavailable", legacy_copy, None, "model_unavailable", None)
    validation = validate_agent_decision(_decode(raw), user_text=user_text)
    if not validation.accepted or validation.decision is None:
        return ShadowObservation("candidate_rejected", legacy_copy, None, validation.rejection_code, None)
    candidate = validation.decision.audit_dict()
    return ShadowObservation("observed", legacy_copy, candidate, None, _match(validation, legacy_copy))
