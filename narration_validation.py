"""Deterministic validation for role narration candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from controlled_knowledge_query import public_visitor_message_or_fallback
from narration_content_plan import NarrationContentPlan
from narration_style_policy import StyleBrief
from role_narration_generation import RoleNarrationCandidate


_INTERNAL = re.compile(
    r"(?:https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|node[_ ]?id|raw[_ ]?chunk|"
    r"rag_tool|llm_think|stop_guidance|narration_content_plan)", re.IGNORECASE
)
_UNAPPROVED_FACT_TRIGGER = re.compile(
    r"(?:\d{3,4}年|公元|朝代|作者|创作者|传说|典故|寓意|象征|第一|唯一|最[具有佳高大]|官方认证|国家级)"
)
_DANGEROUS = re.compile(r"(?:触摸|攀爬|攀坐|跨越护栏|堵住通道|必须回答|强制互动)")


@dataclass(frozen=True)
class NarrationValidationResult:
    validation_status: str
    reason_codes: tuple[str, ...]
    state_writes: tuple[()] = ()
    same_fact_boundary: bool = False
    role_consistent: bool = False
    within_budget: bool = False
    public_message_safe: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_status": self.validation_status,
            "reason_codes": list(self.reason_codes),
            "state_writes": [],
            "same_fact_boundary": self.same_fact_boundary,
            "role_consistent": self.role_consistent,
            "within_budget": self.within_budget,
            "public_message_safe": self.public_message_safe,
        }


def _connector_text(public_text: str, plan: NarrationContentPlan) -> str:
    remaining = public_text
    for fact in sorted(plan.facts, key=lambda item: len(item.statement), reverse=True):
        remaining = remaining.replace(fact.statement, "", 1)
    return remaining


def validate_role_narration(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> NarrationValidationResult:
    reasons: list[str] = []
    allowed_ids = {fact.fact_id for fact in plan.facts}
    required_ids = {fact.fact_id for fact in plan.facts if fact.required}
    used_ids = set(candidate.used_fact_ids)
    if candidate.generation_status != "generated":
        reasons.append(candidate.reason_code or "generation_failed")
    if candidate.style_id != plan.style_id or brief.style_id != plan.style_id:
        reasons.append("style_mismatch")
    if not used_ids.issubset(allowed_ids) or not required_ids.issubset(used_ids):
        reasons.append("fact_id_boundary_violation")
    missing_statements = [fact.fact_id for fact in plan.facts if fact.required and fact.statement not in candidate.public_text]
    if missing_statements:
        reasons.append("approved_statement_not_preserved")
    connector = _connector_text(candidate.public_text, plan)
    if len(connector) > max(120, len(plan.facts) * 60):
        reasons.append("unbounded_role_connectors")
    # Triggers already present in an approved statement are harmless. Only
    # inspect model-added connective prose for new factual assertions.
    if _UNAPPROVED_FACT_TRIGGER.search(connector):
        reasons.append("unapproved_fact_trigger")
    if _INTERNAL.search(candidate.public_text):
        reasons.append("internal_field_leak")
    if _DANGEROUS.search(candidate.public_text):
        reasons.append("unsafe_or_coercive_expression")
    if any(pattern and pattern in candidate.public_text for pattern in brief.prohibited_patterns):
        reasons.append("style_prohibited_pattern")
    if not plan.interaction_allowed and (
        "?" in candidate.public_text
        or "？" in candidate.public_text
        or re.search(r"(?:请你|试着|任务|回答|拍照|跟着做)", candidate.public_text)
    ):
        reasons.append("listen_only_interaction_violation")
    # Conservative speech estimate: four CJK/visible characters per second.
    visible_length = len(re.sub(r"\s+", "", candidate.public_text))
    within_budget = plan.budget_seconds > 0 and visible_length <= plan.budget_seconds * 4
    if not within_budget:
        reasons.append("content_budget_exceeded")
    safe_boundary = public_visitor_message_or_fallback(candidate.public_text) == candidate.public_text
    if not safe_boundary or not candidate.public_text:
        reasons.append("public_message_boundary_rejected")
    same_fact_boundary = not any(
        reason in reasons for reason in (
            "fact_id_boundary_violation", "approved_statement_not_preserved",
            "unapproved_fact_trigger",
        )
    )
    role_consistent = not any(
        reason in reasons for reason in (
            "style_mismatch", "style_prohibited_pattern",
            "listen_only_interaction_violation", "unbounded_role_connectors",
        )
    )
    return NarrationValidationResult(
        validation_status="accepted" if not reasons else "rejected",
        reason_codes=tuple(dict.fromkeys(reasons)),
        same_fact_boundary=same_fact_boundary,
        role_consistent=role_consistent,
        within_budget=within_budget,
        public_message_safe=safe_boundary and not bool(_INTERNAL.search(candidate.public_text)),
    )

