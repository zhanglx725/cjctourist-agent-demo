"""Controlled planning and evidence-grounded rendering for broad knowledge QA.

The language model may classify a visitor question into this module's closed
taxonomy, but it cannot choose arbitrary RAG categories, invent a retrieval
query, or supply Chen Clan Academy facts.  Curated RAG evidence remains the
only factual source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Callable, Iterable


KNOWLEDGE_DOMAIN_CATEGORIES: dict[str, tuple[str, ...]] = {
    "site_overview": ("basic_info", "history_architecture"),
    "history_architecture": ("history_architecture",),
    "visit_service": ("visit_service", "basic_info"),
    "ticketing": ("ticketing_snapshot", "basic_info"),
    "event_notice": ("event_notice",),
    "ornament_craft": ("ornament_craft",),
    "ornament_item": ("ornament_item",),
    "ornament_location": ("ornament_location", "ornament_item"),
}
KNOWLEDGE_DOMAINS = frozenset(KNOWLEDGE_DOMAIN_CATEGORIES)
QUESTION_TYPES = frozenset(
    {
        "definition",
        "time",
        "location",
        "person",
        "material",
        "process",
        "technique",
        "feature",
        "story",
        "meaning",
        "function",
        "composition",
        "list",
        "count",
        "reason",
        "rule",
        "eligibility",
        "method",
        "availability",
        "other",
    }
)
DETAIL_LEVELS = frozenset({"brief", "detailed"})
DYNAMIC_DOMAINS = frozenset({"visit_service", "ticketing", "event_notice"})
AMBIGUOUS_SUBJECTS = frozenset(
    {
        "它",
        "这个",
        "这个东西",
        "这个故事",
        "这个装饰",
        "这种",
        "这里",
        "那里",
        "此处",
    }
)

_DOMAIN_QUERY_HINTS = {
    "site_overview": ("陈家祠", "基本信息", "历史", "建筑"),
    "history_architecture": ("陈家祠", "历史", "建筑", "文化"),
    "visit_service": ("陈家祠", "参观服务", "设施", "规则"),
    "ticketing": ("陈家祠", "购票", "预约", "入馆规则"),
    "event_notice": ("陈家祠", "公告", "展览", "有效期"),
    "ornament_craft": ("陈家祠", "建筑装饰工艺"),
    "ornament_item": ("陈家祠", "建筑装饰", "题材", "寓意"),
    "ornament_location": ("陈家祠", "建筑装饰", "位置"),
}
_QUESTION_QUERY_HINTS = {
    "definition": ("是什么", "定义", "性质"),
    "time": ("时间", "年代", "日期"),
    "location": ("位置", "在哪里", "部位"),
    "person": ("人物", "谁"),
    "material": ("材料", "材质"),
    "process": ("制作流程", "工序"),
    "technique": ("技法", "手法"),
    "feature": ("特点", "形态", "风格"),
    "story": ("故事", "情节", "典故"),
    "meaning": ("寓意", "文化含义", "象征"),
    "function": ("功能", "作用"),
    "composition": ("组成", "结构", "构图"),
    "list": ("有哪些", "代表", "例子"),
    "count": ("数量", "多少"),
    "reason": ("原因", "为什么", "背景"),
    "rule": ("规则", "要求", "限制"),
    "eligibility": ("条件", "资格", "适用人群"),
    "method": ("怎么办", "如何办理", "方式"),
    "availability": ("是否有", "能否使用", "开放情况"),
    "other": (),
}
_FORBIDDEN_VISITOR_TOKENS = (
    ".md",
    "source_ids",
    "chunk_id",
    "title_path",
    "node_id",
    "retrieval_methods",
    "knowledge_base",
    "http://",
    "https://",
    "DSML",
    "tool_calls",
)
_SOURCE_ID = re.compile(r"(?<![A-Za-z0-9])S\d+(?![A-Za-z0-9])")


@dataclass(frozen=True)
class ControlledKnowledgePlan:
    """One validated, read-only interpretation of a knowledge question."""

    domain: str
    question_type: str
    subject_text: str
    detail_level: str
    confidence: str = "high"

    def __post_init__(self) -> None:
        if self.domain not in KNOWLEDGE_DOMAINS:
            raise ValueError(f"unknown knowledge domain: {self.domain}")
        if self.question_type not in QUESTION_TYPES:
            raise ValueError(f"unknown question type: {self.question_type}")
        if self.detail_level not in DETAIL_LEVELS:
            raise ValueError(f"unknown detail level: {self.detail_level}")
        if self.confidence != "high":
            raise ValueError("only high-confidence knowledge plans are actionable")
        normalized_subject = self.subject_text.strip().rstrip("？?。！!")
        if (
            not normalized_subject
            or len(self.subject_text) > 80
            or normalized_subject in AMBIGUOUS_SUBJECTS
        ):
            raise ValueError("subject_text must be a short non-empty visitor span")

    @property
    def categories(self) -> tuple[str, ...]:
        return KNOWLEDGE_DOMAIN_CATEGORIES[self.domain]

    @property
    def is_dynamic(self) -> bool:
        return self.domain in DYNAMIC_DOMAINS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ControlledKnowledgePlan | None":
        if not isinstance(value, dict) or set(value) != {
            "domain",
            "question_type",
            "subject_text",
            "detail_level",
            "confidence",
        }:
            return None
        try:
            return cls(**value)
        except (TypeError, ValueError):
            return None


def build_controlled_retrieval_query(plan: ControlledKnowledgePlan) -> str:
    """Build a stable query from closed hints and an exact visitor subject."""

    terms = (
        plan.subject_text,
        *_DOMAIN_QUERY_HINTS[plan.domain],
        *_QUESTION_QUERY_HINTS[plan.question_type],
    )
    return " ".join(dict.fromkeys(term.strip() for term in terms if term.strip()))


def filter_plan_evidence(
    plan: ControlledKnowledgePlan,
    evidence: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only evidence from the plan's reviewed category boundary."""

    return [
        item
        for item in evidence
        if (
            isinstance(item, dict)
            and item.get("category") in plan.categories
            and str(item.get("content") or "").strip()
        )
    ]


def grounded_answer_prompt(
    plan: ControlledKnowledgePlan,
    evidence: list[dict[str, Any]],
) -> str:
    """Return a strict synthesis prompt whose only facts are evidence payloads."""

    safe_evidence = [
        {
            "content": str(item.get("content") or ""),
            "status": item.get("status"),
            "valid_from": item.get("valid_from"),
            "valid_to": item.get("valid_to"),
            "verified_at": item.get("verified_at"),
        }
        for item in evidence
    ]
    length_rule = (
        "控制在约150至300个中文字符，先用一两句直接回答，再给最多3个必要要点。"
        if plan.detail_level == "brief"
        else "组织为约400至700个中文字符的连贯讲解，按问题逻辑分段，不得截断句子。"
    )
    dynamic_rule = (
        "这是可能变化的信息；必须区分资料快照与实时状态，并以“开放或服务安排可能调整，请以馆方当日公告为准”收束。"
        if plan.is_dynamic
        else "只在有必要时用“馆方公开资料表明”说明证据边界。"
    )
    return (
        "你是陈家祠受控知识讲解器。只根据下方 evidence 回答，不得使用模型记忆补充陈家祠事实。\n"
        f"问题领域：{plan.domain}\n"
        f"问题类型：{plan.question_type}\n"
        f"游客询问对象：{plan.subject_text}\n"
        f"讲解深度：{plan.detail_level}\n"
        f"表达要求：{length_rule}\n"
        "必须直接回答游客所问的方面；不要把检索段落逐条照抄，不要扩写无关的地址、票务、路线或历史。\n"
        "若 evidence 只支持部分答案，明确说清支持到哪里；若存在冲突，说明口径差异，不自行裁决。\n"
        "不得输出文件名、资料标题、原始chunk、来源编号、URL、类别名、节点名、JSON或工具调用文本。\n"
        f"时效要求：{dynamic_rule}\n"
        "evidence：\n"
        + json.dumps(safe_evidence, ensure_ascii=False)
    )


def _visitor_answer_is_safe(message: str) -> bool:
    compact = str(message or "").strip()
    if not compact or len(compact) > 1800:
        return False
    if any(token in compact for token in _FORBIDDEN_VISITOR_TOKENS):
        return False
    return _SOURCE_ID.search(compact) is None


def render_controlled_knowledge_answer(
    plan: ControlledKnowledgePlan,
    evidence: Iterable[dict[str, Any]],
    invoke_model: Callable[[str], str],
) -> str:
    """Synthesize a visitor answer, failing closed on missing or unsafe output."""

    scoped = filter_plan_evidence(plan, evidence)
    if not scoped:
        message = "现有资料不足以可靠回答这个问题，我不会用相邻但无关的信息补答案。"
        if plan.is_dynamic:
            message += " 开放或服务安排可能调整，请以馆方当日公告为准。"
        return message
    try:
        message = str(invoke_model(grounded_answer_prompt(plan, scoped))).strip()
    except Exception:
        message = ""
    if not _visitor_answer_is_safe(message):
        message = (
            "已经找到相关资料，但暂时无法把证据安全整理成游客答案；"
            "请换一种更具体的问法，我不会直接展示检索原文。"
        )
        if plan.is_dynamic:
            message += " 开放或服务安排可能调整，请以馆方当日公告为准。"
    elif plan.is_dynamic and "请以馆方当日公告为准" not in message:
        message = (
            message.rstrip("。")
            + "。开放或服务安排可能调整，请以馆方当日公告为准。"
        )
    return message
