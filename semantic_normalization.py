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
from duration_parser import parse_duration_minutes


CONTROL_CANDIDATE_TYPES = frozenset(
    {
        "none",
        "arrival",
        "request_next_stop",
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
VALID_CANDIDATE_TYPES = frozenset(
    {*CONTROL_CANDIDATE_TYPES, *FACT_CANDIDATE_TO_KIND}
)
MIN_ACTIONABLE_CONFIDENCE = 0.9


# The model may only *propose* an arrival.  These guards keep the raw user
# wording in charge of whether that proposal can be converted into the A1
# vocabulary.  They deliberately reject rather than infer a visitor location.
_ARRIVAL_NEGATION_PATTERNS = (
    r"还没到",
    r"还没(?:抵达|到达|来到|走到|走进)",
    r"没有到",
    r"没有(?:抵达|到达|来到|走到|走进)",
    r"没到",
    r"尚未(?:到|抵达|到达|来到)",
    r"人还没到",
    r"别(?:记录|算|当作).{0,12}到",
    r"不要(?:记录|算|当作).{0,12}到",
)
_ARRIVAL_IN_TRANSIT_PATTERNS = (
    r"快到",
    r"快走到",
    r"正在去",
    r"还在路上",
    r"准备前往",
    r"准备走到",
    r"马上就到",
    r"马上到",
    r"还有.{0,6}步到",
)
_ARRIVAL_DESTINATION_PATTERNS = (
    r"想去",
    r"准备去",
    r"打算去",
    r"接下来去",
    r"带我到",
    r"准备前往",
)
_ARRIVAL_QUESTION_PATTERNS = (
    r"如果.{0,12}到",
    r"到了.{0,12}(?:怎么办|会讲什么)",
    r"是不是到",
    r"你觉得.{0,12}到",
    r"我算到.{0,12}吗",
    r"我算(?:抵达|到达|来到|走到).{0,12}吗",
)
_ARRIVAL_THIRD_PARTY_TERMS = ("朋友", "孩子", "导游")
_ARRIVAL_CONFLICT_TERMS = (
    "跳过", "再详细", "详细讲", "把时间改", "结束路线", "结束游览",
    "顺便", "再讲",
)


def is_safe_arrival_report_text(user_text: str) -> bool:
    """Return whether raw text is an unambiguous first-person arrival report.

    This shared guard is used by both the semantic candidate boundary and A1
    text classification.  It has no node-resolution or state-writing power.
    """
    text = str(user_text or "").strip()
    if not text:
        return False
    if any(re.search(pattern, text) for pattern in (
        *_ARRIVAL_NEGATION_PATTERNS,
        *_ARRIVAL_IN_TRANSIT_PATTERNS,
        *_ARRIVAL_DESTINATION_PATTERNS,
        *_ARRIVAL_QUESTION_PATTERNS,
    )):
        return False
    if "？" in text or "?" in text or any(term in text for term in ("有什么", "讲讲", "哪些")):
        return False
    if any(term in text for term in _ARRIVAL_CONFLICT_TERMS):
        return False
    if "我们" not in text and any(term in text for term in _ARRIVAL_THIRD_PARTY_TERMS):
        return False
    return bool(re.search(r"(?:到|抵达|来到|走到|走进|到位|就在|现在(?:人)?在)", text))


def is_safe_arrival_candidate(user_text: str, candidate: "SemanticCandidate") -> bool:
    """Return whether a validated arrival proposal may enter A1 parsing.

    This is intentionally a pure, conservative *eligibility* check.  It never
    resolves a node, binds a pending stop, or changes state.  Node resolution
    remains in ``tour_intent.resolve_reviewed_node`` and all writes remain in
    ``handle_tour_event``.
    """
    if candidate.candidate_type != "arrival" or not candidate.actionable:
        return False
    # The candidate itself already proves both evidence fields are raw
    # substrings.  This final guard requires an actual arrival/location report
    # rather than accepting any sentence containing a reviewed place name.
    return is_safe_arrival_report_text(user_text)


@dataclass(frozen=True)
class SemanticCandidate:
    """A validated, source-bounded proposal from the semantic recognizer."""

    candidate_type: str = "none"
    evidence_span: str = ""
    confidence: float = 0.0
    location_text: str | None = None
    time_text: str | None = None
    time_role: str | None = None
    knowledge_domain: str | None = None
    question_type: str | None = None
    detail_level: str | None = None

    @property
    def actionable(self) -> bool:
        return (
            self.candidate_type != "none"
            and isinstance(self.confidence, float)
            and self.confidence >= MIN_ACTIONABLE_CONFIDENCE
        )

    # Compatibility accessors are intentionally read-only.  Model JSON and
    # persisted per-turn state use only the v2 schema below.
    @property
    def candidate_kind(self) -> str:
        return self.candidate_type

    @property
    def evidence_text(self) -> str:
        return self.evidence_span

    def to_dict(self) -> dict[str, Any]:
        value = {
            "candidate_type": self.candidate_type,
            "evidence_span": self.evidence_span,
            "confidence": self.confidence,
        }
        if self.candidate_type == "arrival":
            value["location_text"] = self.location_text
        elif self.candidate_type in {"available_duration", "remaining_duration"}:
            value.update({"time_text": self.time_text, "time_role": self.time_role})
        elif self.candidate_type == "knowledge_query":
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
- arrival：用户明确表示自己已经抵达。若原话明确提到地点，可填写 location_text；否则为 null。
- request_next_stop：用户要求前往、查看或继续至当前正式路线的下一站。
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
- evidence_span 必须是原话中连续出现的最短相关片段；不能自行改写对象，也不能只填“它”“这个”“这里”等脱离上下文无法确定的代词。
- arrival 的 location_text 必须是原话中的连续地点片段，不能输出 node_id；没有明确地点时为 null。
- available_duration / remaining_duration 的 time_text 必须是原话中的连续时间片段，time_role 分别为 available / remaining。不能计算或输出分钟数。

普通候选只输出一行 JSON，严格只含 candidate_type、evidence_span、confidence 三个键。
arrival 严格只含 candidate_type、evidence_span、location_text、confidence 四个键。
duration 严格只含 candidate_type、evidence_span、time_text、time_role、confidence 五个键。
knowledge_query 严格只含 candidate_type、evidence_span、confidence、knowledge_domain、question_type、detail_level 六个键。
confidence 必须是 0 到 1 的数字；仅在把握很高时使用不低于 0.90 的值。
禁止输出 node_id、minutes、seconds、deadline、route、route_id、source_ids、query、categories、answer、state_update、tool 或其他任何键。
有疑义时输出 {"candidate_type":"none","evidence_span":"","confidence":0.0}。

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
    base_keys = {"candidate_type", "evidence_span", "confidence"}
    arrival_keys = {*base_keys, "location_text"}
    duration_keys = {*base_keys, "time_text", "time_role"}
    knowledge_keys = {
        *base_keys,
        "knowledge_domain",
        "question_type",
        "detail_level",
    }
    if not isinstance(value, dict):
        return SemanticCandidate()
    actual_keys = frozenset(value)
    if not actual_keys:
        return SemanticCandidate()
    candidate_type = value.get("candidate_type")
    evidence_span = value.get("evidence_span")
    confidence = value.get("confidence")
    if not isinstance(candidate_type, str) or candidate_type not in VALID_CANDIDATE_TYPES:
        return SemanticCandidate()
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        return SemanticCandidate()
    normalized_confidence = float(confidence)
    if candidate_type == "none":
        return (
            SemanticCandidate()
            if actual_keys == frozenset(base_keys) and evidence_span == "" and normalized_confidence < MIN_ACTIONABLE_CONFIDENCE
            else SemanticCandidate()
        )
    if not isinstance(evidence_span, str) or not evidence_span.strip():
        return SemanticCandidate()
    if evidence_span not in user_text:
        return SemanticCandidate()
    if candidate_type == "arrival":
        if actual_keys != frozenset(arrival_keys):
            return SemanticCandidate()
        location_text = value.get("location_text")
        if location_text is not None and (
            not isinstance(location_text, str)
            or not location_text.strip()
            or location_text not in user_text
        ):
            return SemanticCandidate()
        return SemanticCandidate(
            candidate_type, evidence_span, normalized_confidence,
            location_text=location_text,
        )
    if candidate_type in {"available_duration", "remaining_duration"}:
        expected_role = "available" if candidate_type == "available_duration" else "remaining"
        if actual_keys != frozenset(duration_keys):
            return SemanticCandidate()
        time_text = value.get("time_text")
        if (
            not isinstance(time_text, str)
            or not time_text.strip()
            or time_text not in user_text
            or value.get("time_role") != expected_role
        ):
            return SemanticCandidate()
        return SemanticCandidate(
            candidate_type, evidence_span, normalized_confidence,
            time_text=time_text, time_role=expected_role,
        )
    if candidate_type == "knowledge_query":
        if actual_keys != frozenset(knowledge_keys):
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
            candidate_type=candidate_type,
            evidence_span=evidence_span,
            confidence=normalized_confidence,
            knowledge_domain=domain,
            question_type=question_type,
            detail_level=detail_level,
        )
    if actual_keys != frozenset(base_keys):
        return SemanticCandidate()
    return SemanticCandidate(candidate_type, evidence_span, normalized_confidence)


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
    if candidate.candidate_type == "arrival":
        return f"我到{candidate.location_text}了" if candidate.location_text else "我到了"
    if candidate.candidate_type == "request_next_stop":
        return "下一站怎么走"
    if candidate.candidate_type in {"available_duration", "remaining_duration"}:
        parsed = parse_duration_minutes(candidate.time_text or "")
        if not parsed.ok:
            return None
        prefix = "我有" if candidate.time_role == "available" else "我还剩"
        return f"{prefix}{parsed.minutes}分钟"
    if candidate.candidate_type == "route_request":
        return "帮我规划路线"
    if candidate.candidate_type == "route_request_minimize_walking":
        # Preserve the approved route preference in the deterministic C2
        # vocabulary; C2 still owns validation and persistence.
        return "帮我规划一条少走路的路线"
    return None


def canonical_fact_kind(candidate: SemanticCandidate) -> str | None:
    """Map one validated semantic proposal to an existing reviewed fact kind."""

    if not candidate.actionable:
        return None
    return FACT_CANDIDATE_TO_KIND.get(candidate.candidate_type)


def canonical_knowledge_plan(
    candidate: SemanticCandidate,
) -> ControlledKnowledgePlan | None:
    """Map one validated semantic proposal to a read-only knowledge plan."""

    if not candidate.actionable or candidate.candidate_type != "knowledge_query":
        return None
    try:
        return ControlledKnowledgePlan(
            domain=str(candidate.knowledge_domain),
            question_type=str(candidate.question_type),
            subject_text=candidate.evidence_span,
            detail_level=str(candidate.detail_level),
            confidence="high",
        )
    except ValueError:
        return None
