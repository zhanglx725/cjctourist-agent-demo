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
# Natural discourse is a platform capability, not a privilege granted to three
# early pilot personas.  Every approved role gets the same fact boundary and
# safety checks; only the reviewed StyleBrief changes its voice.
PILOT_DISCOURSE_STYLES: frozenset[str] = frozenset()
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
    fact_topics: tuple[str, ...]
    bridge_slots: tuple[DiscourseBridgeSlot, ...]
    max_connector_characters: int
    recent_expressions: tuple[str, ...] = ()

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            # The real claims and identifiers deliberately stay server-side.
            # The model needs only a neutral observation rhythm for each slot;
            # passing reviewed prose here tempted it to paraphrase or embellish
            # names, positions, and object traits outside the fact boundary.
            "fact_slots": [
                {"position": index + 1, "topic_kind": topic}
                for index, topic in enumerate(self.fact_topics)
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
        fact_topics=tuple(fact.topic_kind for fact in plan.facts),
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
    # The deterministic component library is also a reviewed voice reference.
    # Keep it fact-free and small: it should widen the model's phrasing range,
    # not become another template to copy.
    palette_keys = (
        "opening", "space_intro", "craft_intro", "ornament_intro",
        "appreciation", "closing",
    )
    expression_palette = [
        phrase
        for key in palette_keys
        for phrase in brief.point_narration_components.get(key, ())[:3]
        if isinstance(phrase, str) and phrase.strip()
    ]
    payload = {
        "discourse_plan": discourse_plan.to_prompt_dict(),
        "style_brief": {
            "style_id": brief.style_id,
            "persona": brief.persona,
            "generation_policy": brief.generation_policy,
            "acceptance_profile": brief.acceptance_profile,
            "prohibited_patterns": list(brief.prohibited_patterns),
            "expression_palette": expression_palette,
        },
    }
    palette_rule = """
expression_palette 是已审核、且不含事实的声音灵感库。可借鉴其观察动作、节奏和收束方式，但不得逐句照抄；
每次至少用一个具体观察动作来组织表达（例如收近视线、对照、连起关系、回到整体）。避免流水线式重复
“有意思”“抓重点”“找到线索”等口头禅。
"""
    child_expression_rule = """
儿童风格可以使用“像、仿佛、好像、可以把它想成”等明显属于比喻的表达，营造温柔、陪伴、探索和轻微童话感。
这些表达只能描述观看感受或探索节奏，不能新增真实人物、年代、事件、用途、空间关系或传说细节；
不要机械重复“小线索”“新朋友”等口头禅，同一个短句在整组连接语中只能出现一次。
""" if discourse_plan.style_id == "child" else ""
    return """你是成熟的实地导游，而不是模板拼接器。审核事实由服务端持有并原样插入，
你负责把它们组织成游客愿意听下去的、完整而自然的角色讲解。
opening 放在第一条事实之前；bridges 必须逐一对应 bridge_slots；closing 放在最后一条事实之后。
relation=same_unit_continuation 时应自然承接同一对象或工艺，不得提前切换主题；
relation=topic_transition 时才可以转入新的内容类型。输入中没有事实原文、专名或位置；
连接语只可写观察动作、注意顺序、角色关系、节奏和无事实收束。不得猜测或描述任何实体的
名称、位置、颜色、形状、材料、用途、年代、人物、故事、寓意、价值、路线或现场状态。
整组连接语必须自然连贯：让 opening 建立角色与眼前观察目标，让 bridges 解释“为什么现在看下一项”，
让 closing 自然收束。不要逐句评价、机械总结、审核术语和重复口头禅。不要只把角色称谓塞进第一句；
StyleBrief 中的 persona、generation_policy、acceptance_profile 和 few_shot_examples 是本轮角色合同，
请在整组表达的称呼、节奏、观察动作和收束中持续兑现它。
recent_expressions_to_avoid 是当前 Thread 最近已发布的纯表达片段，不含事实；不得原样复用。
不得输出事实原文、事实令牌、Markdown、换行、内部字段、URL 或文件路径。
全部连接语总字符数不得超过 discourse_plan.max_connector_characters。
输出严格一行 JSON，只能包含 schema_version、style_id、opening、bridges、closing、self_check。
schema_version 必须为 role_discourse_candidate_v1；bridges 每项只能包含 slot_id 和 text，顺序不得改变。
self_check 只能包含 added_new_facts、role_consistent、within_budget 三个布尔值。不要输出代码块。
""" + palette_rule + child_expression_rule + "输入：" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


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
    # A slot can contain multiple sentences, so comparing only whole slots
    # misses the duplicate refrain that later causes narration_validation to
    # reject an otherwise safe Active candidate.  Catch it here and let the
    # deterministic scaffold select distinct reviewed components instead.
    sentences = [
        re.sub(r"\s+", "", sentence)
        for text in texts
        for sentence in re.split(r"[。！？!?]+", text)
        if re.sub(r"\s+", "", sentence)
    ]
    if len(sentences) != len(set(sentences)):
        reasons.append("repeated_discourse_sentence")
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
    # Paragraphs are part of meaning: visitors need to see the current focus,
    # then each observation, then a clean close.  Do not collapse an entire
    # stop into the old card-like wall of text.
    paragraphs = [candidate.opening]
    for index, statement in enumerate(discourse_plan.fact_statements):
        paragraph = statement
        if index < len(candidate.bridges):
            paragraph += candidate.bridges[index][1]
        paragraphs.append(paragraph)
    paragraphs.append(candidate.closing)
    return "\n\n".join(part for part in paragraphs if part)


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
