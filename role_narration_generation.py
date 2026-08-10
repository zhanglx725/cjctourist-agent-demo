"""Bounded role narration candidate generation.

The model receives a minimal reviewed StyleBrief and a source-free claim plan.
It cannot retrieve, call tools, or write state. Approved fact statements must
remain verbatim; the model may only arrange them and add bounded role phrasing.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from narration_content_plan import NarrationContentPlan
from narration_style_policy import StyleBrief


CANDIDATE_SCHEMA_VERSION = "role_narration_candidate_v1"
_MODEL_CANDIDATE_FIELDS = frozenset({
    "schema_version", "style_id", "public_text", "used_fact_ids",
    "omitted_fact_ids", "self_check",
})
_CANDIDATE_ENVELOPE_FIELDS = frozenset({
    "schema_version", "generation_status", "reason_code", "style_id",
    "public_text", "used_fact_ids", "omitted_fact_ids", "self_check",
    "model_called", "latency_ms",
})
_SELF_CHECK_FIELDS = frozenset({
    "added_new_facts", "role_consistent", "within_budget",
})
_FACT_TOKEN = re.compile(r"\[\[FACT_\d{3}\]\]")
UNAPPROVED_CONNECTOR_FACT_TRIGGER = re.compile(
    r"(?:\d{3,4}年|公元|朝代|作者|创作者|传说|典故|寓意|象征|第一|唯一|"
    r"最[具有佳高大]|官方认证|国家级)"
)


def role_connector_text(
    public_text: str,
    plan: NarrationContentPlan,
) -> str:
    """Return model prose outside the one immutable copy of each fact."""
    remaining = public_text
    for fact in sorted(plan.facts, key=lambda item: len(item.statement), reverse=True):
        remaining = remaining.replace(fact.statement, "", 1)
    return remaining


def connector_has_unapproved_fact(
    candidate: "RoleNarrationCandidate",
    plan: NarrationContentPlan,
) -> bool:
    return bool(
        candidate.generation_status == "generated"
        and UNAPPROVED_CONNECTOR_FACT_TRIGGER.search(
            role_connector_text(candidate.public_text, plan)
        )
    )


def _plan_output_limits(plan: NarrationContentPlan) -> tuple[int, int]:
    approved_fact_characters = sum(
        len(re.sub(r"\s+", "", fact.statement))
        for fact in plan.facts
    )
    allocated_seconds = plan.allocated_content_seconds
    if allocated_seconds <= 0 and approved_fact_characters:
        # Compatibility fallback for old serialized plans and unit fixtures.
        # Live plans carry E5's authoritative allocated duration.
        allocated_seconds = math.ceil(approved_fact_characters / 4)
    remaining_seconds = max(0, plan.budget_seconds - allocated_seconds)
    max_connector_characters = max(
        0,
        min(
            120,
            len(plan.facts) * 60,
            remaining_seconds * 4,
        ),
    )
    max_public_characters = approved_fact_characters + max_connector_characters
    return max_public_characters, max_connector_characters


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
    # Keep every reviewed fact but omit planning fields that cannot affect the
    # expression candidate. This reduces prompt echo without exposing route,
    # state, retrieval, or coverage data and without weakening validation.
    required_facts = [fact for fact in plan.facts if fact.required]
    optional_facts = [fact for fact in plan.facts if not fact.required]
    max_public_characters, max_role_connector_characters = _plan_output_limits(plan)
    payload = {
        "style_brief": brief.to_dict(),
        "content_plan": {
            "schema_version": plan.schema_version,
            "style_id": plan.style_id,
            "language": plan.language,
            "budget_seconds": plan.budget_seconds,
            "facts": [
                {
                    **fact.to_dict(),
                    "public_text_token": f"[[FACT_{index:03d}]]",
                }
                for index, fact in enumerate(plan.facts)
            ],
            "must_include": list(plan.must_include),
            "must_not_claim": list(plan.must_not_claim),
            "interaction_allowed": plan.interaction_allowed,
            "max_public_text_characters": max_public_characters,
            "max_role_connector_characters": max_role_connector_characters,
        },
    }
    shape_example = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "style_id": plan.style_id,
        "public_text": "".join(
            f"[[FACT_{index:03d}]]"
            for index, fact in enumerate(plan.facts)
            if fact.required
        ),
        "used_fact_ids": [fact.fact_id for fact in required_facts],
        "omitted_fact_ids": [fact.fact_id for fact in optional_facts],
        "self_check": {
            "added_new_facts": False,
            "role_consistent": True,
            "within_budget": True,
        },
    }
    return """你是受控的导游表达实现器，不是事实检索器，也不是路线控制器。
content_plan.facts[*].statement 是不可编辑的审核原文，仅用于理解；不得把 statement 本身重打、
概括或意译到 public_text。public_text 必须使用同一事实的 public_text_token 代表完整事实块。
每个 required=true 的 public_text_token 必须原样出现且只出现一次。角色化文字只能放在 token
之前、两个 token 之间或全部 token 之后，不得修改或拆分 token。所有 required=true 的
fact_id 必须列入 used_fact_ids，且不得列入
omitted_fact_ids。只允许省略 required=false 的事实。
public_text 去除事实 token 后的全部角色连接文字，总字符数不得超过
content_plan.max_role_connector_characters；public_text 恢复事实后的总字符数不得超过
content_plan.max_public_text_characters。若连接预算为 0，只输出 required token，不加任何文字。
你可以调整完整事实块的顺序，并添加简短的角色化称呼、开场、连接和收束，但不得新增人物、年代、
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
    if not isinstance(value, str):
        return None
    text = value.lstrip("\ufeff").strip()
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
    if not isinstance(value, Mapping) or frozenset(value) != _MODEL_CANDIDATE_FIELDS:
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
        or frozenset(checks) != _SELF_CHECK_FIELDS
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


def _hydrate_fact_tokens(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
) -> RoleNarrationCandidate:
    """Replace model-arranged opaque tokens with immutable reviewed facts."""
    if candidate.generation_status != "generated":
        return candidate
    text = candidate.public_text
    used_ids = set(candidate.used_fact_ids)
    omitted_ids = set(candidate.omitted_fact_ids)
    all_ids = {fact.fact_id for fact in plan.facts}
    required_ids = {fact.fact_id for fact in plan.facts if fact.required}
    if (
        len(used_ids) != len(candidate.used_fact_ids)
        or len(omitted_ids) != len(candidate.omitted_fact_ids)
        or used_ids & omitted_ids
        or used_ids | omitted_ids != all_ids
        or not required_ids.issubset(used_ids)
    ):
        return _failed(
            plan.style_id, "invalid_fact_id_partition",
            candidate.latency_ms, model_called=True,
        )
    known_tokens = {
        f"[[FACT_{index:03d}]]": fact
        for index, fact in enumerate(plan.facts)
    }
    if any(token not in known_tokens for token in _FACT_TOKEN.findall(text)):
        return _failed(
            plan.style_id, "invalid_fact_placeholders",
            candidate.latency_ms, model_called=True,
        )
    connector_text = text
    for token, fact in known_tokens.items():
        token_count = text.count(token)
        statement_count = text.count(fact.statement)
        expected = fact.fact_id in used_ids
        # Exact statements remain accepted for backwards-compatible test
        # fixtures, but live prompts use opaque tokens. A used fact must occur
        # exactly once in one representation; an omitted fact must not occur.
        if (token_count + statement_count) != (1 if expected else 0):
            return _failed(
                plan.style_id, "invalid_fact_placeholders",
                candidate.latency_ms, model_called=True,
            )
        connector_text = connector_text.replace(token, "")
        connector_text = connector_text.replace(fact.statement, "")
        text = text.replace(token, fact.statement)
    max_public_characters, max_connector_characters = _plan_output_limits(plan)
    if (
        len(re.sub(r"\s+", "", connector_text)) > max_connector_characters
        or len(re.sub(r"\s+", "", text)) > max_public_characters
    ):
        return _failed(
            plan.style_id, "candidate_budget_exceeded",
            candidate.latency_ms, model_called=True,
        )
    return RoleNarrationCandidate(
        style_id=candidate.style_id,
        public_text=text,
        used_fact_ids=candidate.used_fact_ids,
        omitted_fact_ids=candidate.omitted_fact_ids,
        self_check=dict(candidate.self_check),
        model_called=candidate.model_called,
        latency_ms=candidate.latency_ms,
    )


def generate_role_narration(
    plan: NarrationContentPlan,
    brief: StyleBrief,
    invoke_model: Callable[[str], str],
) -> RoleNarrationCandidate:
    if plan.status != "ready" or brief.style_id != plan.style_id:
        return _failed(plan.style_id, "plan_or_style_not_ready")
    allocated_seconds = plan.allocated_content_seconds
    if allocated_seconds <= 0:
        approved_fact_characters = sum(
            len(re.sub(r"\s+", "", fact.statement)) for fact in plan.facts
        )
        allocated_seconds = math.ceil(approved_fact_characters / 4)
    if plan.budget_seconds <= 0 or allocated_seconds > plan.budget_seconds:
        return _failed(plan.style_id, "fact_budget_infeasible")
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
    candidate = _hydrate_fact_tokens(candidate, plan)
    connector_fact_violation = connector_has_unapproved_fact(candidate, plan)
    if candidate.generation_status == "generated" and not connector_fact_violation:
        return candidate
    # One bounded repair is allowed for structural errors or factual connector
    # prose. Facts and StyleBrief remain authoritative; the repair receives no
    # state, tools or RAG and validation remains fail-closed.
    repair_instruction = (
        "事实 token 之外的连接语新增或改写了事实。请让所有事实内容只通过原样的 "
        "FACT token 表达；连接语只能是简短称呼、过渡或收束，不得复述、概括或推断事实。"
        if connector_fact_violation
        else ""
    )
    repair_prompt = (
        prompt
        + "\n" + repair_instruction
        + "上一输出未通过 JSON Schema、事实占位符或连接语事实边界约束。请重新输出且只输出规定的 JSON 对象。"
        + "不得解释错误，不得增加字段；required token 必须各出现一次。上一输出："
        + str(raw)[:500]
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
    repaired = validate_candidate_shape(
        _decode(repaired_raw), expected_style_id=plan.style_id,
        latency_ms=total_latency,
    )
    return _hydrate_fact_tokens(repaired, plan)


def role_narration_candidate_from_dict(value: Mapping[str, Any] | None) -> RoleNarrationCandidate | None:
    """Parse only the internal candidate envelope emitted by this module.

    The model wire object has six fields.  Graph state stores that object in a
    ten-field audit envelope.  Keeping this parser strict prevents a second,
    permissive schema from accepting unknown fields after generation has
    already failed closed.
    """
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _CANDIDATE_ENVELOPE_FIELDS
        or value.get("schema_version") != CANDIDATE_SCHEMA_VERSION
        or value.get("generation_status") not in {"generated", "rejected"}
        or not isinstance(value.get("style_id"), str)
        or not isinstance(value.get("public_text"), str)
        or not isinstance(value.get("used_fact_ids"), list)
        or not all(isinstance(item, str) for item in value.get("used_fact_ids", []))
        or not isinstance(value.get("omitted_fact_ids"), list)
        or not all(isinstance(item, str) for item in value.get("omitted_fact_ids", []))
        or not isinstance(value.get("self_check"), dict)
        or not all(isinstance(item, bool) for item in value.get("self_check", {}).values())
        or not isinstance(value.get("model_called"), bool)
        or type(value.get("latency_ms")) is not int
        or value.get("latency_ms") < 0
        or (
            value.get("reason_code") is not None
            and not isinstance(value.get("reason_code"), str)
        )
    ):
        return None
    if value.get("generation_status") == "generated" and frozenset(value["self_check"]) != _SELF_CHECK_FIELDS:
        return None
    if value.get("generation_status") == "rejected" and value["public_text"]:
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
