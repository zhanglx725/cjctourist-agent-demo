"""D3 deterministic retrieval of D1-gated research-summary cards.

Research cards remain attributed interpretations.  This module never loads a
card file directly and never treats a research summary as site-fact evidence.
"""

from __future__ import annotations

from typing import Any, Callable

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry


COMPARISON_CUES = ("区别", "异同", "相比", "相较", "对照", "不同在哪里", "比较", "对比", "vs", "VS")
RESEARCH_CUES = (
    "论文如何", "论文怎样", "从研究", "研究角度", "学术", "研究者", "有没有相关研究",
    "研究依据", "建筑学", "民俗学", "研究方法", "研究限制", "这个研究", "该研究",
)


def is_explicit_research_question(query: str) -> bool:
    """Recognize only explicit research questions; comparisons stay for D4."""
    return not any(cue in query for cue in COMPARISON_CUES) and any(cue in query for cue in RESEARCH_CUES)


def _labels(card: KnowledgeCard) -> list[str]:
    raw = card.raw_payload
    return [
        *[str(value) for value in raw.get("topic_tags", []) if isinstance(value, str)],
        *[str(value) for value in raw.get("supported_questions", []) if isinstance(value, str)],
        str(raw.get("title_zh") or ""),
        str(raw.get("research_question") or ""),
    ]


def _eligible_research_cards(registry: dict[str, KnowledgeCard]) -> list[KnowledgeCard]:
    return [
        card for card in registry.values()
        if card.card_type == "research_summary"
        and card.runtime_status in {"enabled", "attributed_only"}
        and "attributed_research_viewpoint" in card.allowed_capabilities
        and card.raw_payload.get("status") != "background"
    ]


def _score(card: KnowledgeCard, query: str, current_node_id: str | None) -> int:
    raw = card.raw_payload
    normalized = query.casefold()
    supported = raw.get("supported_questions", [])
    supported_hit = sum(1 for value in supported if isinstance(value, str) and any(tag in normalized for tag in raw.get("topic_tags", []) if tag))
    topic_hits = sum(1 for tag in raw.get("topic_tags", []) if isinstance(tag, str) and tag.casefold() in normalized)
    title_hits = sum(1 for value in _labels(card) if value and value.casefold() in normalized)
    content_score = (60 if supported_hit else 0) + topic_hits * 20 + min(title_hits, 3) * 5
    # A current-node relation is only a tie-breaker among cards that already
    # match the research question.  It must never turn an unrelated question
    # into an apparent exact research-card match.
    if content_score == 0:
        return 0
    node_bonus = 20 if current_node_id and current_node_id in raw.get("applicable_node_ids", []) else 0
    # Whole-site cards (empty applicable nodes) deliberately receive no node bonus.
    return content_score + node_bonus


def retrieve_research_cards(
    user_query: str,
    *,
    current_node_id: str | None = None,
    registry_loader: Callable[[], dict[str, KnowledgeCard]] = build_registry,
    limit: int = 2,
) -> dict[str, Any]:
    """Return at most two eligible cards in reproducible relevance order."""
    if not is_explicit_research_question(user_query):
        return {"status": "not_research_question", "cards": []}
    try:
        cards = _eligible_research_cards(registry_loader())
    except Exception:
        return {"status": "registry_unavailable", "cards": []}
    ranked = [( _score(card, user_query, current_node_id), card) for card in cards]
    ranked = [(score, card) for score, card in ranked if score > 0]
    ranked.sort(key=lambda item: (-item[0], item[1].card_id))
    selected = []
    for _, card in ranked[:max(1, min(limit, 2))]:
        raw = card.raw_payload
        selected.append(
            {
                "title_zh": raw.get("title_zh"),
                "author_position": raw.get("author_position"),
                "method_and_evidence": list(raw.get("method_and_evidence", [])),
                "guide_safe_takeaway": raw.get("guide_safe_takeaway"),
                "agreement_and_limits": dict(raw.get("agreement_and_limits", {})),
                "integration_rule": raw.get("integration_rule"),
                "citation": (raw.get("source") or {}).get("citation"),
                "runtime_status": card.runtime_status,
                "applicable_here": bool(current_node_id and current_node_id in raw.get("applicable_node_ids", [])),
            }
        )
    return {"status": "ok" if selected else "no_eligible_match", "cards": selected}


def _citation_label(citation: str | None) -> str:
    if not citation:
        return "相关研究"
    return citation.split("https", 1)[0].strip().rstrip("。")


def format_research_answer(
    context: dict[str, Any],
    *,
    knowledge_level: str = "general",
    base_evidence: list[dict[str, Any]] | None = None,
) -> str:
    """Render attribution and limits without exposing internal card metadata."""
    cards = context.get("cards") or []
    if not cards:
        return "暂未找到可安全引用、且与该问题直接匹配的研究摘要；我只能依据基础资料继续说明。"
    lines = ["从研究视角看："]
    for card in cards:
        lines.append(f"- {_citation_label(card.get('citation'))} 的研究指出：{card.get('author_position') or card.get('guide_safe_takeaway')}")
        if knowledge_level in {"enthusiast", "professional"}:
            methods = [str(item) for item in card.get("method_and_evidence", []) if item]
            if methods:
                lines.append(f"  研究主要采用：{'；'.join(methods[:2])}。")
        limits = (card.get("agreement_and_limits") or {}).get("limits")
        if limits:
            lines.append(f"  适用范围与限制：{limits}")
    if base_evidence:
        source_ids = []
        for item in base_evidence:
            source_ids.extend(item.get("source_ids") or [])
        if source_ids:
            lines.append(f"基础事实仍应以本地知识库证据交叉核对（来源：{'、'.join(dict.fromkeys(source_ids))}）。")
    return "\n".join(lines)
