"""Fact-anchored, model-written discourse for natural compact narration.

The model owns expression slots only. Reviewed facts never enter the response
schema and are inserted verbatim by ``compose_role_discourse`` after the slot
candidate has passed deterministic validation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from narration_content_plan import NarrationContentPlan
from narration_style_policy import StyleBrief
from role_narration_generation import (
    UNAPPROVED_CONNECTOR_FACT_TRIGGER,
    role_connector_character_limit,
)


DISCOURSE_SCHEMA_VERSION = "role_discourse_candidate_v1"
PILOT_DISCOURSE_STYLES = frozenset({
    "child", "ancient_scholar", "dominant_ceo",
})
_CANDIDATE_FIELDS = frozenset({
    "schema_version", "style_id", "opening", "bridges", "closing", "self_check",
})
_BRIDGE_FIELDS = frozenset({"slot_id", "text"})
_SELF_CHECK_FIELDS = frozenset({
    "added_new_facts", "role_consistent", "within_budget",
})
_INTERNAL = re.compile(
    r"(?:\[\[FACT_|https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|"
    r"node[_ ]?id|raw[_ ]?chunk|stop_guidance|narration_content_plan)",
    re.IGNORECASE,
)
_UNSAFE = re.compile(r"(?:触摸|攀爬|攀坐|跨越护栏|堵住通道|必须回答|强制互动)")
_INTERACTION = re.compile(r"(?:\?|？|请你|试着|任务|回答|拍照|跟着做)")
_BAD_LAYOUT = re.compile(r"(?:\n|【|】|[。！？]{2,}|[，、]{2,}|～|^\s*(?:#|[-*+]\s|\d+[.)、]))")


@dataclass(frozen=True)
class DiscourseBridgeSlot:
    slot_id: str
    relation: str
    left_topic: str
    right_topic: str

    def to_dict(self) -> dict[str, str]:
        return {
            "slot_id": self.slot_id,
            "relation": self.relation,
            "left_topic": self.left_topic,
            "right_topic": self.right_topic,
        }


@dataclass(frozen=True)
class RoleDiscoursePlan:
    style_id: str
    fact_ids: tuple[str, ...]
    fact_statements: tuple[str, ...]
    bridge_slots: tuple[DiscourseBridgeSlot, ...]
    max_connector_characters: int
    recent_expressions: tuple[str, ...] = ()

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "facts": [
                {"fact_id": fact_id, "statement": statement}
                for fact_id, statement in zip(self.fact_ids, self.fact_statements)
            ],
            "bridge_slots": [slot.to_dict() for slot in self.bridge_slots],
            "max_connector_characters": self.max_connector_characters,
            "recent_expressions_to_avoid": list(self.recent_expressions),
        }


@dataclass(frozen=True)
class RoleDiscourseCandidate:
    style_id: str
    opening: str
    bridges: tuple[tuple[str, str], ...]
    closing: str
    self_check: dict[str, bool]
    status: str = "generated"
    reason_codes: tuple[str, ...] = ()
    schema_version: str = DISCOURSE_SCHEMA_VERSION

    def connector_text(self) -> str:
        return "".join((self.opening, *(text for _, text in self.bridges), self.closing))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "style_id": self.style_id,
            "opening": self.opening,
            "bridges": [
                {"slot_id": slot_id, "text": text}
                for slot_id, text in self.bridges
            ],
            "closing": self.closing,
            "self_check": dict(self.self_check),
        }


def build_role_discourse_plan(
    plan: NarrationContentPlan,
    *,
    recent_expressions: tuple[str, ...] = (),
) -> RoleDiscoursePlan | None:
    if (
        plan.status != "ready"
        or plan.scaffold_mode != "compact"
        or plan.style_id not in PILOT_DISCOURSE_STYLES
        or not plan.facts
    ):
        return None
    slots = []
    for index, (left, right) in enumerate(zip(plan.facts, plan.facts[1:])):
        relation = (
            "same_unit_continuation"
            if left.unit_id == right.unit_id
            else "topic_transition" if left.topic_kind != right.topic_kind
            else "same_topic_new_unit"
        )
        slots.append(DiscourseBridgeSlot(
            slot_id=f"bridge:{index:03d}",
            relation=relation,
            left_topic=left.topic_kind,
            right_topic=right.topic_kind,
        ))
    return RoleDiscoursePlan(
        style_id=plan.style_id,
        fact_ids=tuple(fact.fact_id for fact in plan.facts),
        fact_statements=tuple(fact.statement for fact in plan.facts),
        bridge_slots=tuple(slots),
        max_connector_characters=role_connector_character_limit(plan),
        recent_expressions=tuple(
            value.strip() for value in recent_expressions[-12:]
            if isinstance(value, str) and value.strip()
        ),
    )


def role_discourse_prompt(
    discourse_plan: RoleDiscoursePlan,
    brief: StyleBrief,
) -> str:
    payload = {
        "discourse_plan": discourse_plan.to_prompt_dict(),
        "style_brief": {
            "style_id": brief.style_id,
            "persona": brief.persona,
            "generation_policy": brief.generation_policy,
            "acceptance_profile": brief.acceptance_profile,
            "prohibited_patterns": list(brief.prohibited_patterns),
        },
    }
    return """你是受控导游的表达规划器。审核事实由服务端持有并原样插入，你只能生成事实之间的自然连接语。
opening 放在第一条事实之前；bridges 必须逐一对应 bridge_slots；closing 放在最后一条事实之后。
relation=same_unit_continuation 时应自然承接同一对象或工艺，不得提前切换主题；
relation=topic_transition 时才可以转入新的内容类型。连接语不得复述、改写或补充任何事实，
不得增加人物、年代、故事、寓意、评价、位置、路线、现场状态或官方背书。
整组连接语必须自然连贯，避免逐句评价、机械总结、审核术语和重复口头禅。
recent_expressions_to_avoid 是当前 Thread 最近已发布的纯表达片段，不含事实；不得原样复用。
不得输出事实原文、事实令牌、Markdown、换行、内部字段、URL 或文件路径。
全部连接语总字符数不得超过 discourse_plan.max_connector_characters。
输出严格一行 JSON，只能包含 schema_version、style_id、opening、bridges、closing、self_check。
schema_version 必须为 role_discourse_candidate_v1；bridges 每项只能包含 slot_id 和 text，顺序不得改变。
self_check 只能包含 added_new_facts、role_consistent、within_budget 三个布尔值。不要输出代码块。
输入：""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _rejected(style_id: str, *reasons: str) -> RoleDiscourseCandidate:
    return RoleDiscourseCandidate(
        style_id=style_id, opening="", bridges=(), closing="", self_check={},
        status="rejected", reason_codes=tuple(dict.fromkeys(reasons)),
    )


def parse_and_validate_role_discourse(
    value: str | Mapping[str, Any] | None,
    discourse_plan: RoleDiscoursePlan,
    brief: StyleBrief,
    *,
    interaction_allowed: bool,
) -> RoleDiscourseCandidate:
    try:
        raw = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return _rejected(discourse_plan.style_id, "invalid_discourse_json")
    if not isinstance(raw, Mapping) or frozenset(raw) != _CANDIDATE_FIELDS:
        return _rejected(discourse_plan.style_id, "invalid_discourse_schema")
    checks = raw.get("self_check")
    bridges = raw.get("bridges")
    if (
        raw.get("schema_version") != DISCOURSE_SCHEMA_VERSION
        or raw.get("style_id") != discourse_plan.style_id
        or not isinstance(raw.get("opening"), str)
        or not isinstance(raw.get("closing"), str)
        or not isinstance(bridges, list)
        or not isinstance(checks, dict)
        or frozenset(checks) != _SELF_CHECK_FIELDS
        or not all(isinstance(item, bool) for item in checks.values())
    ):
        return _rejected(discourse_plan.style_id, "invalid_discourse_fields")
    expected_slot_ids = [slot.slot_id for slot in discourse_plan.bridge_slots]
    parsed_bridges: list[tuple[str, str]] = []
    for item in bridges:
        if (
            not isinstance(item, Mapping)
            or frozenset(item) != _BRIDGE_FIELDS
            or not isinstance(item.get("slot_id"), str)
            or not isinstance(item.get("text"), str)
        ):
            return _rejected(discourse_plan.style_id, "invalid_discourse_bridge")
        parsed_bridges.append((item["slot_id"], item["text"].strip()))
    if [slot_id for slot_id, _ in parsed_bridges] != expected_slot_ids:
        return _rejected(discourse_plan.style_id, "discourse_bridge_order_changed")
    candidate = RoleDiscourseCandidate(
        style_id=discourse_plan.style_id,
        opening=raw["opening"].strip(),
        bridges=tuple(parsed_bridges),
        closing=raw["closing"].strip(),
        self_check=dict(checks),
    )
    texts = (candidate.opening, *(text for _, text in candidate.bridges), candidate.closing)
    reasons: list[str] = []
    if any(not text for text in texts):
        reasons.append("empty_discourse_slot")
    connector = candidate.connector_text()
    if len(re.sub(r"\s+", "", connector)) > discourse_plan.max_connector_characters:
        reasons.append("discourse_budget_exceeded")
    if _INTERNAL.search(connector):
        reasons.append("discourse_internal_leak")
    if _UNSAFE.search(connector):
        reasons.append("unsafe_discourse_expression")
    if _BAD_LAYOUT.search(connector):
        reasons.append("invalid_discourse_layout")
    if UNAPPROVED_CONNECTOR_FACT_TRIGGER.search(connector):
        reasons.append("unapproved_discourse_fact_trigger")
    if any(statement and statement in connector for statement in discourse_plan.fact_statements):
        reasons.append("discourse_repeats_reviewed_fact")
    normalized = [re.sub(r"\s+", "", text) for text in texts]
    if len(normalized) != len(set(normalized)):
        reasons.append("repeated_discourse_slot")
    recent = {
        re.sub(r"\s+", "", value)
        for value in discourse_plan.recent_expressions
        if value
    }
    if any(value in recent for value in normalized):
        reasons.append("recent_discourse_expression_reused")
    forbidden = tuple(brief.acceptance_profile.get("forbidden_markers", ())) + tuple(brief.prohibited_patterns)
    if any(marker and marker in connector for marker in forbidden):
        reasons.append("discourse_forbidden_marker")
    required_markers = tuple(
        marker for marker in brief.acceptance_profile.get("required_markers", ())
        if isinstance(marker, str) and marker
    )
    if required_markers and not any(marker in connector for marker in required_markers):
        reasons.append("discourse_style_marker_missing")
    interaction_mode = brief.acceptance_profile.get("interaction_contract", {}).get("mode")
    if (not interaction_allowed or interaction_mode == "none") and _INTERACTION.search(connector):
        reasons.append("discourse_interaction_violation")
    if checks.get("added_new_facts") or not checks.get("role_consistent") or not checks.get("within_budget"):
        reasons.append("discourse_self_check_failed")
    return _rejected(discourse_plan.style_id, *reasons) if reasons else candidate


def compose_role_discourse(
    candidate: RoleDiscourseCandidate,
    discourse_plan: RoleDiscoursePlan,
) -> str:
    if candidate.status != "generated" or candidate.style_id != discourse_plan.style_id:
        return ""
    parts = [candidate.opening]
    for index, statement in enumerate(discourse_plan.fact_statements):
        parts.append(statement)
        if index < len(candidate.bridges):
            parts.append(candidate.bridges[index][1])
    parts.append(candidate.closing)
    return "".join(parts)


def remember_discourse_expressions(
    connector_text: str,
    recent_expressions: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Keep only bounded, fact-free sentence fragments for Thread dedupe."""
    new_expressions = [
        value.strip()
        for value in re.findall(r"[^。！？]+[。！？]", connector_text)
        if value.strip()
    ]
    return tuple(dict.fromkeys([
        *recent_expressions, *new_expressions,
    ]))[-12:]
