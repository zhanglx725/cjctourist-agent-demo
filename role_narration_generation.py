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
    # A point narration needs a short role phrase before, between, and after
    # immutable fact blocks.  The former whole-message cap often left room for
    # only an opening, so long explanations became generic after sentence one.
    # This remains bounded by the authoritative time budget.
    structured_cap = min(360, 20 + 24 * (len(plan.facts) + 3))
    max_connector_characters = max(0, min(structured_cap, remaining_seconds * 4))
    max_public_characters = approved_fact_characters + max_connector_characters
    return max_public_characters, max_connector_characters


def role_connector_character_limit(plan: NarrationContentPlan) -> int:
    """Expose the single budget formula used by generation and validation."""
    return _plan_output_limits(plan)[1]


def _component(
    brief: StyleBrief,
    kind: str,
    index: int,
    *,
    previous: str = "",
) -> str:
    values = brief.point_narration_components.get(kind, ())
    if not values:
        return ""
    normalized = tuple(str(value).strip() for value in values if str(value).strip())
    if not normalized:
        return ""
    for offset in range(len(normalized)):
        selected = normalized[(index + offset) % len(normalized)]
        if selected != previous:
            return selected
    return normalized[index % len(normalized)]


def apply_point_narration_scaffold(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
    *,
    compact: bool | None = None,
) -> RoleNarrationCandidate:
    """Interleave immutable facts with reviewed persona-only components.

    The model still supplies the strict token envelope.  Once its fact
    partition is valid, its free-form connector prose is deliberately not
    published: this deterministic composer guarantees that the same role is
    audible at the opening, middle, and closing without altering any fact.
    """
    if candidate.generation_status != "generated":
        return candidate
    required_components = {
        "opening", "appreciation", "closing",
        *(f"{topic}_{kind}" for topic in ("space", "craft", "ornament")
          for kind in ("intro", "observation", "transition")),
    }
    if not all(brief.point_narration_components.get(key) for key in required_components):
        return _failed(plan.style_id, "style_components_unavailable", candidate.latency_ms, model_called=True)
    ordered_facts = [fact for fact in plan.facts if fact.fact_id in candidate.used_fact_ids]
    if not ordered_facts:
        return _failed(plan.style_id, "no_used_facts_for_scaffold", candidate.latency_ms, model_called=True)
    parts = [_component(brief, "opening", 0)]
    previous_component = parts[0]
    for index, fact in enumerate(ordered_facts):
        is_unit_start = index == 0 or ordered_facts[index - 1].unit_id != fact.unit_id
        if is_unit_start:
            intro = _component(
                brief, f"{fact.topic_kind}_intro", index,
                previous=previous_component,
            )
            if intro and intro != previous_component:
                parts.append(intro)
                previous_component = intro
        parts.append(fact.statement)
        if not compact and index < len(ordered_facts) - 1:
            next_fact = ordered_facts[index + 1]
            kind = "observation" if next_fact.unit_id == fact.unit_id else "transition"
            bridge = _component(
                brief, f"{fact.topic_kind}_{kind}", index,
                previous=previous_component,
            )
            if bridge and bridge != previous_component:
                parts.append(bridge)
                previous_component = bridge
    if not compact:
        appreciation = _component(
            brief, "appreciation", len(ordered_facts),
            previous=previous_component,
        )
        if appreciation and appreciation != previous_component:
            parts.append(appreciation)
            previous_component = appreciation
    closing = _component(
        brief, "closing", len(ordered_facts), previous=previous_component,
    )
    if closing and closing != previous_component:
        parts.append(closing)
    public_text = "".join(part for part in parts if part)
    if len(re.sub(r"\s+", "", role_connector_text(public_text, plan))) > role_connector_character_limit(plan):
        return _failed(plan.style_id, "style_scaffold_budget_exceeded", candidate.latency_ms, model_called=True)
    return RoleNarrationCandidate(
        style_id=candidate.style_id,
        public_text=public_text,
        used_fact_ids=candidate.used_fact_ids,
        omitted_fact_ids=candidate.omitted_fact_ids,
        self_check=candidate.self_check,
        model_called=candidate.model_called,
        latency_ms=candidate.latency_ms,
    )


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
            "requested_scope": plan.requested_scope,
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
style_brief.acceptance_profile 是本次点位讲解的审核表达合同。仅对你新增的角色连接文字执行：
1. 用 point_narration_strategy 组织开场、事实之间的连接与收束；
2. 在连接文字中满足 required_markers 的至少
   rhythm.min_marker_groups 组，不足时宁可少写并由系统回退，不能伪造事实；
3. 不得使用 forbidden_markers，并遵守 rhythm 的 sentence_length 与 pacing；
4. interaction_contract.mode=none 或 content_plan.interaction_allowed=false 时，绝不提出问题、
   任务、拍照或动作要求；其他 mode 也不得超过 interaction_contract.max_requests。
few_shot_examples 仅示范语气、节奏和事实块周围的连接方式；其中 input_facts 不是可新增事实。
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
    ) + """

最终令牌协议（优先于前文所有角色表达指令）：服务端会确定性生成全部角色开场、观察、承接和收束。
你的 public_text 必须且只能由已给出的 public_text_token 连续组成，不得加入任何其他字符，
包括普通文字、称呼、空格、换行、标点、波浪号、问题、互动或 Markdown；不得改变 token 顺序。
这不是风格缺失：风格文字由服务端在令牌水合后添加。只输出严格 JSON 对象。
"""


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
    found_tokens = _FACT_TOKEN.findall(text)
    if any(token not in known_tokens for token in found_tokens) or not found_tokens:
        return _failed(
            plan.style_id, "invalid_fact_placeholders",
            candidate.latency_ms, model_called=True,
        )
    expected_tokens = [token for token, fact in known_tokens.items() if fact.fact_id in used_ids]
    if found_tokens != expected_tokens:
        return _failed(
            plan.style_id, "invalid_fact_token_order",
            candidate.latency_ms, model_called=True,
        )
    if text != "".join(expected_tokens):
        return _failed(
            plan.style_id, "model_connector_text_forbidden",
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


def _requires_unmodified_validation(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> bool:
    """Do not hide unsafe model prose by replacing it with a style scaffold."""
    if candidate.generation_status != "generated":
        return True
    connector = role_connector_text(candidate.public_text, plan)
    if connector_has_unapproved_fact(candidate, plan):
        return True
    if re.search(r"(?:source[_ ]?ids?|node[_ ]?id|https?://|file://|[A-Za-z]:\\\\)", candidate.public_text, re.I):
        return True
    if re.search(r"(?:[。！？]{2,}|[，、]{2,}|[，。！？]\s*[，。！？]|～)", candidate.public_text):
        return True
    sentences = [piece.strip() for piece in re.split(r"[。！？\n]+", connector) if piece.strip()]
    if len(sentences) != len(set(sentences)):
        return True
    forbidden = tuple(brief.acceptance_profile.get("forbidden_markers", ())) + tuple(brief.prohibited_patterns)
    if any(marker and marker in candidate.public_text for marker in forbidden):
        return True
    contract = brief.acceptance_profile.get("interaction_contract", {})
    if not plan.interaction_allowed or contract.get("mode") == "none":
        if re.search(r"(?:\?|？|请你|试着|任务|回答|拍照|跟着做)", candidate.public_text):
            return True
    return False


def generate_role_narration(
    plan: NarrationContentPlan,
    brief: StyleBrief,
    invoke_model: Callable[[str], str],
    *,
    compact: bool | None = None,
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
    # One request only: malformed output, fact drift, unsafe prose, and
    # budget failure are all handed to narration_validation for the existing
    # deterministic legacy fallback.  Retrying used to extend a visitor turn
    # and could make a bad first response look safe after its prose vanished.
    if _requires_unmodified_validation(candidate, plan, brief):
        return candidate
    return apply_point_narration_scaffold(
        candidate, plan, brief,
        compact=plan.scaffold_mode == "compact" if compact is None else compact,
    )


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
