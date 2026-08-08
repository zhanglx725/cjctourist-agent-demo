"""Bounded role narration candidate generation.

The model receives a minimal reviewed StyleBrief and a source-free claim plan.
It cannot retrieve, call tools, or write state. Approved fact statements must
remain verbatim; the model may only arrange them and add bounded role phrasing.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from narration_content_plan import NarrationContentPlan
from narration_style_policy import StyleBrief


CANDIDATE_SCHEMA_VERSION = "role_narration_candidate_v1"


@dataclass(frozen=True)
class RoleNarrationCandidate:
    style_id: str
    public_text: str
    used_fact_ids: tuple[str, ...]
    omitted_fact_ids: tuple[str, ...]
    self_check: dict[str, bool]
    model_called: bool
    latency_ms: int
    generation_status: str = "generated"
    reason_code: str | None = None
    schema_version: str = CANDIDATE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation_status": self.generation_status,
            "reason_code": self.reason_code,
            "style_id": self.style_id,
            "public_text": self.public_text,
            "used_fact_ids": list(self.used_fact_ids),
            "omitted_fact_ids": list(self.omitted_fact_ids),
            "self_check": dict(self.self_check),
            "model_called": self.model_called,
            "latency_ms": self.latency_ms,
        }


def role_narration_prompt(plan: NarrationContentPlan, brief: StyleBrief) -> str:
    payload = {
        "style_brief": brief.to_dict(),
        "content_plan": plan.to_dict(),
    }
    first_fact = plan.facts[0] if plan.facts else None
    shape_example = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "style_id": plan.style_id,
        "public_text": first_fact.statement if first_fact else "",
        "used_fact_ids": [first_fact.fact_id] if first_fact else [],
        "omitted_fact_ids": [fact.fact_id for fact in plan.facts[1:]],
        "self_check": {
            "added_new_facts": False,
            "role_consistent": True,
            "within_budget": True,
        },
    }
    return """你是受控的导游表达实现器，不是事实检索器，也不是路线控制器。
只能使用输入 content_plan.facts 中的事实。每条 statement 必须逐字原样出现在 public_text 中；
你可以调整事实顺序，并添加简短的角色化称呼、开场、连接和收束，但不得新增人物、年代、
故事、寓意、排名、认证、现场对象或路线信息。不得回答计划之外的问题。
不得输出文件路径、URL、source ID、节点 ID、工具名称或任何内部字段。
若 interaction_allowed=false，不得使用问号、提问、任务、拍照或动作要求。
输出严格的一行 JSON，且只能包含：schema_version、style_id、public_text、used_fact_ids、
omitted_fact_ids、self_check。schema_version 必须为 role_narration_candidate_v1。
self_check 只能包含 added_new_facts、role_consistent、within_budget 三个布尔值。
不要输出 Markdown 代码块。合法输出形状示例：\n""" + json.dumps(
        shape_example, ensure_ascii=False, separators=(",", ":")
    ) + "\n输入如下：\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def _decode(value: str) -> Mapping[str, Any] | None:
    text = str(value).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _failed(style_id: str, reason: str, latency_ms: int = 0, *, model_called: bool = False) -> RoleNarrationCandidate:
    return RoleNarrationCandidate(
        style_id=style_id, public_text="", used_fact_ids=(), omitted_fact_ids=(),
        self_check={}, model_called=model_called, latency_ms=latency_ms,
        generation_status="rejected", reason_code=reason,
    )


def validate_candidate_shape(
    value: Mapping[str, Any] | None,
    *,
    expected_style_id: str,
    latency_ms: int,
) -> RoleNarrationCandidate:
    expected = {
        "schema_version", "style_id", "public_text", "used_fact_ids",
        "omitted_fact_ids", "self_check",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        return _failed(expected_style_id, "invalid_candidate_schema", latency_ms, model_called=True)
    checks = value.get("self_check")
    if (
        value.get("schema_version") != CANDIDATE_SCHEMA_VERSION
        or value.get("style_id") != expected_style_id
        or not isinstance(value.get("public_text"), str)
        or not isinstance(value.get("used_fact_ids"), list)
        or not all(isinstance(item, str) for item in value.get("used_fact_ids", []))
        or not isinstance(value.get("omitted_fact_ids"), list)
        or not all(isinstance(item, str) for item in value.get("omitted_fact_ids", []))
        or not isinstance(checks, dict)
        or set(checks) != {"added_new_facts", "role_consistent", "within_budget"}
        or not all(isinstance(item, bool) for item in checks.values())
    ):
        return _failed(expected_style_id, "invalid_candidate_fields", latency_ms, model_called=True)
    return RoleNarrationCandidate(
        style_id=expected_style_id,
        public_text=str(value["public_text"]).strip(),
        used_fact_ids=tuple(value["used_fact_ids"]),
        omitted_fact_ids=tuple(value["omitted_fact_ids"]),
        self_check=dict(checks), model_called=True, latency_ms=latency_ms,
    )


def generate_role_narration(
    plan: NarrationContentPlan,
    brief: StyleBrief,
    invoke_model: Callable[[str], str],
) -> RoleNarrationCandidate:
    if plan.status != "ready" or brief.style_id != plan.style_id:
        return _failed(plan.style_id, "plan_or_style_not_ready")
    started = time.perf_counter()
    prompt = role_narration_prompt(plan, brief)
    try:
        raw = invoke_model(prompt)
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return _failed(plan.style_id, f"model_unavailable:{type(exc).__name__}", latency, model_called=True)
    latency = int((time.perf_counter() - started) * 1000)
    candidate = validate_candidate_shape(
        _decode(raw), expected_style_id=plan.style_id, latency_ms=latency,
    )
    if candidate.generation_status == "generated":
        return candidate
    # One bounded schema-only repair is allowed. The same facts and StyleBrief
    # remain authoritative; the repair call receives no state, tools or RAG.
    repair_prompt = (
        prompt
        + "\n上一输出未通过 JSON Schema。请重新输出且只输出规定的 JSON 对象。"
        + "不得解释错误，不得增加字段。上一输出："
        + str(raw)[:2000]
    )
    try:
        repaired_raw = invoke_model(repair_prompt)
    except Exception as exc:
        total_latency = int((time.perf_counter() - started) * 1000)
        return _failed(
            plan.style_id, f"schema_repair_unavailable:{type(exc).__name__}",
            total_latency, model_called=True,
        )
    total_latency = int((time.perf_counter() - started) * 1000)
    return validate_candidate_shape(
        _decode(repaired_raw), expected_style_id=plan.style_id,
        latency_ms=total_latency,
    )


def role_narration_candidate_from_dict(value: Mapping[str, Any] | None) -> RoleNarrationCandidate | None:
    if not isinstance(value, Mapping) or value.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        return None
    try:
        return RoleNarrationCandidate(
            style_id=str(value.get("style_id") or "neutral"),
            public_text=str(value.get("public_text") or ""),
            used_fact_ids=tuple(value.get("used_fact_ids", [])),
            omitted_fact_ids=tuple(value.get("omitted_fact_ids", [])),
            self_check=dict(value.get("self_check") or {}),
            model_called=bool(value.get("model_called")),
            latency_ms=int(value.get("latency_ms") or 0),
            generation_status=str(value.get("generation_status") or "rejected"),
            reason_code=value.get("reason_code"),
        )
    except (TypeError, ValueError):
        return None
