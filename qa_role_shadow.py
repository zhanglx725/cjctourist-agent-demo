"""Read-only role-expression planning for deterministic tour QA answers.

The authoritative QA node has already completed retrieval, grounding and
public-safety filtering before this module runs.  The role layer receives only
that public answer as one immutable fact block.  It never receives evidence,
source identifiers, route data or mutable state.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from narration_content_plan import NarrationContentPlan, NarrationFact
from role_mode_shadow import ROLE_MODE_IDS
from narration_style_policy import StyleBrief
from role_narration_generation import RoleNarrationCandidate


QA_PLAN_SCHEMA_VERSION = "qa_content_plan_v1"
QA_SCENE_KINDS = frozenset({"tour_qa", "qa_follow_up_detail"})


def qa_role_components(brief: StyleBrief, scene_kind: str) -> dict[str, str]:
    """Return reviewed, fact-free QA phrases for one role and scene."""
    components = brief.point_narration_components
    opening = next(iter(components.get("opening", ())), "")
    closing = next(iter(components.get("closing", ())), "")
    listen_only = brief.style_id == "listen_only"
    return {
        "opening": opening,
        "direct_answer": "直接回答是：" if scene_kind == "tour_qa" else "接着刚才的问题补充：",
        "follow_up": (
            "本次回答到这里。" if listen_only
            else "如需继续，可以再问一个具体细节。" if scene_kind == "tour_qa"
            else "以上是本次追问范围内的补充。"
        ),
        "uncertainty": "现有审核信息只能确认到这里。",
        "closing": closing,
    }


def apply_qa_role_scaffold(
    candidate: RoleNarrationCandidate,
    plan: "QaContentPlan",
    brief: StyleBrief,
) -> RoleNarrationCandidate:
    if candidate.generation_status != "generated":
        return candidate
    approved = plan.legacy_public_message
    if candidate.used_fact_ids != ("qa:approved_answer",) or approved not in candidate.public_text:
        return candidate
    components = qa_role_components(brief, plan.scene_kind)
    public_text = "".join((
        components["opening"], components["direct_answer"], approved,
        components["follow_up"], components["closing"],
    ))
    return RoleNarrationCandidate(
        style_id=candidate.style_id, public_text=public_text,
        used_fact_ids=candidate.used_fact_ids, omitted_fact_ids=candidate.omitted_fact_ids,
        self_check=candidate.self_check, model_called=candidate.model_called,
        latency_ms=candidate.latency_ms,
    )


@dataclass(frozen=True)
class QaContentPlan:
    scene_kind: str
    legacy_public_message: str
    narration_plan: NarrationContentPlan
    status: str = "ready"
    reason_codes: tuple[str, ...] = ()
    schema_version: str = QA_PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "scene_kind": self.scene_kind,
            "legacy_public_message": self.legacy_public_message,
            "narration_plan": self.narration_plan.to_dict(),
        }


def _rejected(reason: str, scene_kind: str) -> QaContentPlan:
    return QaContentPlan(
        scene_kind=scene_kind,
        legacy_public_message="",
        narration_plan=NarrationContentPlan(
            stop_id="qa",
            style_id="neutral",
            language="zh",
            budget_seconds=0,
            facts=(),
            must_include=(),
            already_covered=(),
            must_not_claim=(),
            interaction_allowed=False,
            status="rejected",
            reason_codes=(reason,),
        ),
        status="rejected",
        reason_codes=(reason,),
    )


def build_qa_content_plan(
    *,
    legacy_public_message: str,
    scene_kind: str,
    role_mode: Mapping[str, Any] | None,
    language: str = "zh",
) -> QaContentPlan:
    """Wrap one approved QA answer in a strict, source-free expression plan."""
    if scene_kind not in QA_SCENE_KINDS:
        return _rejected("unsupported_qa_scene", scene_kind)
    text = str(legacy_public_message or "").strip()
    if not text:
        return _rejected("approved_qa_answer_unavailable", scene_kind)
    role = dict(role_mode or {})
    if role.get("status") == "clarification":
        return _rejected("role_mode_clarification", scene_kind)
    selected = role.get("selected_style_id")
    style_id = selected if role.get("status") == "selected" else "neutral"
    if style_id not in ROLE_MODE_IDS:
        return _rejected("unsupported_role_mode", scene_kind)
    approved_seconds = max(1, math.ceil(len(re.sub(r"\s+", "", text)) / 4))
    # The immutable answer has already consumed its factual duration.  The
    # bounded remainder is only for role connectors and cannot add facts.
    budget_seconds = approved_seconds + 30
    narration_plan = NarrationContentPlan(
        stop_id=f"qa:{scene_kind}",
        style_id=style_id,
        language=language if language in {"zh", "en"} else "zh",
        budget_seconds=budget_seconds,
        allocated_content_seconds=approved_seconds,
        facts=(NarrationFact(
            fact_id="qa:approved_answer",
            semantic_role="approved_qa_answer",
            statement=text,
            required=True,
        ),),
        must_include=("approved_qa_answer",),
        already_covered=(),
        must_not_claim=(
            "new_fact", "new_source", "new_route_or_location",
            "internal_identifier", "state_change",
        ),
        interaction_allowed=style_id != "listen_only",
    )
    return QaContentPlan(
        scene_kind=scene_kind,
        legacy_public_message=text,
        narration_plan=narration_plan,
    )


def qa_content_plan_from_dict(value: Mapping[str, Any] | None) -> QaContentPlan | None:
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != QA_PLAN_SCHEMA_VERSION
        or value.get("scene_kind") not in QA_SCENE_KINDS
        or not isinstance(value.get("legacy_public_message"), str)
        or not isinstance(value.get("reason_codes"), list)
    ):
        return None
    from narration_content_plan import narration_content_plan_from_dict

    narration_plan = narration_content_plan_from_dict(value.get("narration_plan"))
    if narration_plan is None:
        return None
    return QaContentPlan(
        scene_kind=str(value["scene_kind"]),
        legacy_public_message=str(value["legacy_public_message"]),
        narration_plan=narration_plan,
        status=str(value.get("status") or "rejected"),
        reason_codes=tuple(str(item) for item in value.get("reason_codes", [])),
    )


__all__ = [
    "QA_PLAN_SCHEMA_VERSION",
    "QA_SCENE_KINDS",
    "QaContentPlan",
    "build_qa_content_plan",
    "qa_content_plan_from_dict",
]
