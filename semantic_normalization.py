"""Bounded semantic normalization for visitor control language.

This module is deliberately *not* a second intent router.  A language model
may only propose one small, whitelisted control candidate; deterministic
parsers, reviewed-node resolution and the A1 event adapter still decide
whether anything can execute.  In particular, a model can never provide a
node ID, a route, a cultural fact, or a VisitorProfile patch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from controlled_knowledge_query import (
    DETAIL_LEVELS,
    KNOWLEDGE_DOMAINS,
    QUESTION_TYPES,
    ControlledKnowledgePlan,
)


CONTROL_CANDIDATE_KINDS = frozenset(
    {
        "none",
        "generic_arrival",
        "available_duration",
        "remaining_duration",
        "route_request",
        "route_request_minimize_walking",
        "knowledge_query",
    }
)
FACT_CANDIDATE_TO_KIND = {
    "fact_construction_start": "construction_start",
    "fact_construction_completion": "construction_completion",
    "fact_construction_duration": "construction_duration",
    "fact_site_address": "site_address",
    "fact_closed_day": "closed_day",
    "fact_closing_time": "closing_time",
    "fact_last_admission": "last_admission",
    "fact_afternoon_entry_cutoff": "afternoon_entry_cutoff",
    "fact_designer_and_foundation_date": "designer_and_foundation_date",
    "fact_museum_establishment": "museum_establishment",
    "fact_museum_reopening": "museum_reopening",
    "fact_museum_renaming": "museum_renaming",
}
VALID_CANDIDATE_KINDS = frozenset(
    {*CONTROL_CANDIDATE_KINDS, *FACT_CANDIDATE_TO_KIND}
)
VALID_CONFIDENCES = frozenset({"high", "low"})
_MAX_MINUTES = 720


@dataclass(frozen=True)
class SemanticCandidate:
    """A validated, source-bounded proposal from the semantic recognizer."""

    candidate_kind: str = "none"
    evidence_text: str = ""
    confidence: str = "low"
    minutes: int | None = None
    knowledge_domain: str | None = None
    question_type: str | None = None
    detail_level: str | None = None

    @property
    def actionable(self) -> bool:
        return self.candidate_kind != "none" and self.confidence == "high"

    def to_dict(self) -> dict[str, Any]:
        value = {
            "candidate_kind": self.candidate_kind,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
            "minutes": self.minutes,
        }
        if self.candidate_kind == "knowledge_query":
            value.update(
                {
                    "knowledge_domain": self.knowledge_domain,
                    "question_type": self.question_type,
                    "detail_level": self.detail_level,
                }
            )
        return value


def recognition_prompt(user_text: str) -> str:
    """Return a strict, fact-free prompt for one model classification call."""
    return f"""你是受控语义识别器，不是导游。只判断用户这句话是否明确表达以下一个操作或事实问题；
不能回答问题、不能补充事实、不能猜测地点、不能生成检索词、类别、node_id、路线或画像。

操作候选：
- generic_arrival：用户明确表示自己已经抵达，但没有明确点位。
- available_duration：用户明确给出本次可用于游览的时长。
- remaining_duration：用户明确给出游览途中剩余时长。
- route_request：用户请求规划游览路线。
- route_request_minimize_walking：用户请求规划路线，并明确要求少走路/步行最少。

审核事实问题候选：
- fact_construction_start：询问陈家祠开始筹建、始建或启动建设的年份。
- fact_construction_completion：询问陈家祠落成、建成或竣工年份。
- fact_construction_duration：询问从筹建到落成经历多久。
- fact_site_address：询问陈家祠地址或位于哪里。
- fact_closed_day：询问固定哪天、星期几、什么时候不开放或休馆；没有“几点”等钟点表达。
- fact_closing_time：询问开放日几点闭馆、关门或结束开放。
- fact_last_admission：询问最晚几点还能进入、几点以后不能进、停止入场或入馆时间。
- fact_afternoon_entry_cutoff：明确询问下午场的检票、入场或入馆截止时间。
- fact_designer_and_foundation_date：询问设计者或确切奠基日期。
- fact_museum_establishment：询问广东民间工艺馆或现博物馆的机构成立时间。
- fact_museum_reopening：询问广东民间工艺馆复馆、重新对外开放的时间。
- fact_museum_renaming：询问广东民间工艺馆何时更名为广东民间工艺博物馆。

通用知识问题候选：
- knowledge_query：问题属于陈家祠现有知识库，但不属于上面的审核单一事实，也没有被工艺、术语、研究、比较、拍照或点位专项通道覆盖。
  knowledge_domain 只能是：site_overview、history_architecture、visit_service、ticketing、event_notice、ornament_craft、ornament_item、ornament_location。
  领域含义：
  - site_overview：场馆名称、身份、总体概况及概览类问题；
  - history_architecture：历史沿革、营建背景、建筑格局、空间形制与文化解释；
  - visit_service：讲解、寄存、交通、停车、设施、参观规则和到访服务；
  - ticketing：门票、预约、优惠、适用人群和入馆票务规则；
  - event_notice：临时公告、展览、活动及带有效期的信息；
  - ornament_craft：装饰工艺的材料、制作流程、技法与工艺特点；
  - ornament_item：具体装饰作品、人物题材、故事、寓意与构图；
  - ornament_location：具体装饰对象或题材位于哪里、哪个建筑部位。
  question_type 只能是：definition、time、location、person、material、process、technique、feature、story、meaning、function、composition、list、count、reason、rule、eligibility、method、availability、other。
  detail_level 只能是 brief 或 detailed；只有用户明确要求详细、深入、展开时才选 detailed，否则选 brief。
- none：其他所有情况，包括多意图问题、模糊问题、无法判断知识领域、地点猜测和与陈家祠无关的问题。

区分边界：
- “哪天/星期几/休息日/啥时候不开放”且没有钟点表达，属于 fact_closed_day。
- “几点闭馆/几点关门”属于 fact_closing_time。
- “最晚几点能进/几点后不能进入”属于 fact_last_admission，不等同于闭馆时间。
- 同一句同时要求两个不同候选时输出 none/low，不自行拆分。
- knowledge_query 的 evidence_text 必须是原话中表示询问对象的最短连续片段，例如“三顾茅庐”“建筑布局”“无障碍设施”；不能自行改写对象，也不能只填“它”“这个”“这里”等脱离上下文无法确定的代词。

普通候选只输出一行 JSON，严格只含 candidate_kind、evidence_text、confidence、minutes 四个键。
knowledge_query 严格只含 candidate_kind、evidence_text、confidence、minutes、knowledge_domain、question_type、detail_level 七个键。
evidence_text 必须是用户原话中连续出现的最短片段；confidence 只能是 high 或 low。
只有明确时长的两个 duration 类型才填写 minutes（正整数分钟）；其他类型 minutes 为 null。
有疑义时输出 none/low。

用户原话：{user_text}"""


def _decode_json(model_output: str) -> dict[str, Any] | None:
    text = str(model_output).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def validate_candidate(user_text: str, value: dict[str, Any] | None) -> SemanticCandidate:
    """Fail closed unless the proposed candidate is small and auditable."""
    base_keys = {"candidate_kind", "evidence_text", "confidence", "minutes"}
    knowledge_keys = {
        *base_keys,
        "knowledge_domain",
        "question_type",
        "detail_level",
    }
    if not isinstance(value, dict):
        return SemanticCandidate()
    actual_keys = frozenset(value)
    if actual_keys not in {frozenset(base_keys), frozenset(knowledge_keys)}:
        return SemanticCandidate()
    kind = value.get("candidate_kind")
    evidence_text = value.get("evidence_text")
    confidence = value.get("confidence")
    minutes = value.get("minutes")
    if not isinstance(kind, str) or kind not in VALID_CANDIDATE_KINDS:
        return SemanticCandidate()
    if not isinstance(evidence_text, str) or not evidence_text.strip():
        return SemanticCandidate()
    if evidence_text not in user_text:
        return SemanticCandidate()
    if confidence not in VALID_CONFIDENCES:
        return SemanticCandidate()
    if kind == "knowledge_query":
        if set(value) != knowledge_keys or minutes is not None:
            return SemanticCandidate()
        domain = value.get("knowledge_domain")
        question_type = value.get("question_type")
        detail_level = value.get("detail_level")
        if (
            domain not in KNOWLEDGE_DOMAINS
            or question_type not in QUESTION_TYPES
            or detail_level not in DETAIL_LEVELS
        ):
            return SemanticCandidate()
        return SemanticCandidate(
            kind,
            evidence_text,
            confidence,
            None,
            domain,
            question_type,
            detail_level,
        )
    if set(value) != base_keys:
        return SemanticCandidate()
    if kind in {"available_duration", "remaining_duration"}:
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 < minutes <= _MAX_MINUTES:
            return SemanticCandidate()
    elif minutes is not None:
        return SemanticCandidate()
    return SemanticCandidate(kind, evidence_text, confidence, minutes)


def recognize_semantic_candidate(
    user_text: str,
    invoke_model: Callable[[str], str],
) -> SemanticCandidate:
    """Ask for a candidate once; any model or schema error is a safe no-op."""
    try:
        raw = invoke_model(recognition_prompt(user_text))
    except Exception:
        return SemanticCandidate()
    return validate_candidate(user_text, _decode_json(raw))


def canonical_control_text(candidate: SemanticCandidate) -> str | None:
    """Map an approved proposal to existing deterministic parser language."""
    if not candidate.actionable:
        return None
    if candidate.candidate_kind == "generic_arrival":
        return "我到了"
    if candidate.candidate_kind == "available_duration":
        return f"我有{candidate.minutes}分钟"
    if candidate.candidate_kind == "remaining_duration":
        return f"我还剩{candidate.minutes}分钟"
    if candidate.candidate_kind == "route_request":
        return "帮我规划路线"
    if candidate.candidate_kind == "route_request_minimize_walking":
        # Preserve the approved route preference in the deterministic C2
        # vocabulary; C2 still owns validation and persistence.
        return "帮我规划一条少走路的路线"
    return None


def canonical_fact_kind(candidate: SemanticCandidate) -> str | None:
    """Map one validated semantic proposal to an existing reviewed fact kind."""

    if not candidate.actionable:
        return None
    return FACT_CANDIDATE_TO_KIND.get(candidate.candidate_kind)


def canonical_knowledge_plan(
    candidate: SemanticCandidate,
) -> ControlledKnowledgePlan | None:
    """Map one validated semantic proposal to a read-only knowledge plan."""

    if not candidate.actionable or candidate.candidate_kind != "knowledge_query":
        return None
    try:
        return ControlledKnowledgePlan(
            domain=str(candidate.knowledge_domain),
            question_type=str(candidate.question_type),
            subject_text=candidate.evidence_text,
            detail_level=str(candidate.detail_level),
            confidence=candidate.confidence,
        )
    except ValueError:
        return None
