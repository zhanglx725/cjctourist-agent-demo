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


CONTROL_CANDIDATE_KINDS = frozenset(
    {
        "none",
        "generic_arrival",
        "available_duration",
        "remaining_duration",
        "route_request",
        "route_request_minimize_walking",
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

    @property
    def actionable(self) -> bool:
        return self.candidate_kind != "none" and self.confidence == "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_kind": self.candidate_kind,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
            "minutes": self.minutes,
        }


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
- none：其他所有情况，包括多意图问题、模糊问题、未列出的知识主题和地点猜测。

区分边界：
- “哪天/星期几/休息日/啥时候不开放”且没有钟点表达，属于 fact_closed_day。
- “几点闭馆/几点关门”属于 fact_closing_time。
- “最晚几点能进/几点后不能进入”属于 fact_last_admission，不等同于闭馆时间。
- 同一句同时要求两个不同候选时输出 none/low，不自行拆分。

只输出一行 JSON，严格只含 candidate_kind、evidence_text、confidence、minutes 四个键。
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
    if not isinstance(value, dict) or set(value) != {
        "candidate_kind", "evidence_text", "confidence", "minutes"
    }:
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
