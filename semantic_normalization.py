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


VALID_CANDIDATE_KINDS = frozenset(
    {
        "none",
        "generic_arrival",
        "available_duration",
        "remaining_duration",
        "route_request",
        "route_request_minimize_walking",
    }
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
    return f"""你是受控语义识别器，不是导游。只判断用户这句话是否表达以下一种操作；
不能回答问题、不能补充事实、不能猜测地点、不能生成 node_id、路线或画像。

候选类型：
- generic_arrival：用户明确表示自己已经抵达，但没有明确点位。
- available_duration：用户明确给出本次可用于游览的时长。
- remaining_duration：用户明确给出游览途中剩余时长。
- route_request：用户请求规划游览路线。
- route_request_minimize_walking：用户请求规划路线，并明确要求少走路/步行最少。
- none：其他所有情况，包括知识问题、模糊时间、未明确到达、地点猜测。

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
