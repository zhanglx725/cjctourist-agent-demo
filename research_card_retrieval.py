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
    "研究依据", "建筑学", "民俗学", "研究方法", "研究限制", "这个研究", "该研究", "研究",
)

# These are deliberately broad *subject* words, rather than a second list of
# research-intent cues.  A visitor rarely repeats a card's full topic tag (for
# example, they ask about "建筑" instead of "建筑装饰").  Matching these words
# against the reviewed card metadata keeps that natural phrasing useful without
# treating an arbitrary current-node card as a match.
SUBJECT_CUES = (
    "建筑", "装饰", "雕塑", "空间", "工艺", "布局", "营建", "庭院", "连廊",
    "灰塑", "木雕", "石雕", "陶塑", "屋脊", "月台", "栏板", "中轴", "通风",
    "保护", "旗杆", "科举", "题材", "象征", "书院", "祠堂",
)
GENERAL_RESEARCH_WORDS = (
    "介绍一下", "介绍", "一下", "这里的", "这里", "这座", "这个", "该处", "此处",
    "陈家祠", "陈氏书院", "学术研究", "学术", "研究", "论文", "文献", "相关", "方面",
    "关于", "请问", "请", "的", "了", "吗", "呢", "？", "?", "，", ",", "。", ".", "、", " ",
)
GENERAL_OVERVIEW_CARD_IDS = (
    "research_004_spatial_characteristics",
    "research_006_sculptural_metaphor",
)
# A small, editorially reviewed bridge for common umbrella terms.  These
# words do not always occur verbatim in topic_tags, but the selected cards
# directly study the named craft/arts subject.  Keeping this mapping explicit
# avoids broadening a current-node association into an unrelated answer.
SUBJECT_CARD_FALLBACKS = {
    "建筑": (
        "research_004_spatial_characteristics",
        "research_016_academy_ancestral_program",
    ),
    "工艺": (
        "research_003_ridge_pottery_colour",
        "research_008_grey_plaster_lions",
    ),
    "技艺": (
        "research_003_ridge_pottery_colour",
        "research_008_grey_plaster_lions",
    ),
    "艺术": (
        "research_003_ridge_pottery_colour",
        "research_006_sculptural_metaphor",
    ),
    "雕刻": (
        "research_006_sculptural_metaphor",
        "research_008_grey_plaster_lions",
    ),
    "陶塑": ("research_003_ridge_pottery_colour",),
}


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
    metadata = " ".join(_labels(card))
    subject_hits = sum(
        1 for cue in SUBJECT_CUES
        if cue in normalized and cue in metadata.casefold()
    )
    content_score = (60 if supported_hit else 0) + topic_hits * 20 + min(title_hits, 3) * 5 + subject_hits * 12
    # A current-node relation is only a tie-breaker among cards that already
    # match the research question.  It must never turn an unrelated question
    # into an apparent exact research-card match.
    if content_score == 0:
        return 0
    node_bonus = 20 if current_node_id and current_node_id in raw.get("applicable_node_ids", []) else 0
    # Whole-site cards (empty applicable nodes) deliberately receive no node bonus.
    return content_score + node_bonus


def _is_general_research_overview(query: str) -> bool:
    """Whether the visitor asks for a site-level research introduction.

    This is intentionally narrow: removing research phrasing must leave no
    subject word.  Questions such as "这里的建筑研究" retain "建筑" and therefore
    still require a metadata match.
    """
    remainder = query.casefold()
    for word in GENERAL_RESEARCH_WORDS:
        remainder = remainder.replace(word, "")
    return not remainder.strip()


def _subject_fallback_ids(query: str) -> tuple[str, ...]:
    """Return only the reviewed card IDs curated for an umbrella subject."""
    normalized = query.casefold()
    for subject, card_ids in SUBJECT_CARD_FALLBACKS.items():
        if subject in normalized:
            return card_ids
    return ()


def _has_exact_topic_match(cards: list[KnowledgeCard], query: str) -> bool:
    """Keep a card's own precise topic tag ahead of umbrella aliases."""
    normalized = query.casefold()
    return any(
        isinstance(tag, str) and tag.casefold() in normalized
        for card in cards
        for tag in card.raw_payload.get("topic_tags", [])
    )


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
    ranked = [(_score(card, user_query, current_node_id), card) for card in cards]
    fallback_ids = _subject_fallback_ids(user_query)
    if fallback_ids and not _has_exact_topic_match(cards, user_query):
        ranked = [
            (
                40 + (20 if current_node_id and current_node_id in card.applicable_node_ids else 0),
                card,
            )
            for card in cards
            if card.card_id in fallback_ids
        ]
    elif not any(score for score, _ in ranked) and _is_general_research_overview(user_query):
        # A plainly worded request for an academic introduction is a valid
        # request for the reviewed overview cards.  Prefer cards applicable at
        # the current stop, but never use a node relation for a specific,
        # otherwise unmatched subject question.
        ranked = [
            (
                (40 if card.card_id in GENERAL_OVERVIEW_CARD_IDS else 0)
                + (20 if current_node_id and current_node_id in card.applicable_node_ids else 0),
                card,
            )
            for card in cards
            if card.card_id in GENERAL_OVERVIEW_CARD_IDS
        ]
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


def _public_research_limit(limit: object) -> str:
    """Keep a card's boundary while using visitor-safe language.

    The final public-message guard correctly treats editorial terms such as
    ``未核验`` as internal workflow language.  That must not discard an
    otherwise valid research answer: the visitor-facing equivalent makes the
    same claim boundary clear without exposing the review workflow.
    """
    text = str(limit or "").strip()
    return text.replace("未核验", "尚待现场资料佐证")


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
        limits = _public_research_limit(
            (card.get("agreement_and_limits") or {}).get("limits")
        )
        if limits:
            lines.append(f"  适用范围与限制：{limits}")
    # ``base_evidence`` remains available to the caller for audit and Trace.
    # Internal source IDs are never appended to the visitor-facing research
    # summary; attribution above uses the reviewed human-readable citation.
    return "\n".join(lines)
