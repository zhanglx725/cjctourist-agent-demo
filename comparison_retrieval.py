"""Retrieve reviewed comparison cards without turning them into facts.

Comparison cards are guide-writing context, not a replacement for local RAG
evidence.  In particular, cards marked ``research_only`` may only be surfaced
for research-oriented questions and must retain their attribution boundary.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml


ROOT = Path(__file__).parent
COMPARISON_FILE = ROOT / "data" / "chen_clan_academy" / "comparisons" / "comparison_cards_v0.yaml"

GENERAL_ALLOWED_STRENGTHS = {"confirmed", "cautious"}
COMPARISON_CUES = ("比较", "对比", "区别", "不同", "差别", "相比", "相较", "vs")
RESEARCH_CUES = ("研究", "论文", "文献", "学术", "资料", "来源", "引用")


@lru_cache(maxsize=1)
def load_comparison_cards() -> dict[str, dict[str, Any]]:
    """Load cards by ID; malformed records are ignored rather than guessed."""
    data = yaml.safe_load(COMPARISON_FILE.read_text(encoding="utf-8")) or {}
    return {
        card["comparison_id"]: card
        for card in data.get("cards", [])
        if isinstance(card, dict) and card.get("comparison_id")
    }


def _is_comparison_question(query: str) -> bool:
    normalized = query.casefold()
    return any(cue in normalized for cue in COMPARISON_CUES)


def _is_research_question(query: str) -> bool:
    normalized = query.casefold()
    return any(cue in normalized for cue in RESEARCH_CUES)


def _card_labels(card: dict[str, Any]) -> list[str]:
    """Return conservative labels that a visitor can explicitly mention."""
    labels = [card.get("theme_zh", ""), *card.get("comparison_objects", [])]
    # These words occur in card themes and make craft questions retrievable
    # without using an opaque semantic model.
    labels.extend(
        {
            "craft_special_topic": ["灰塑", "砖塑", "陶塑", "屋脊", "琉璃"],
            "same_region_craft_context": ["灰塑", "资政大夫祠"],
            "same_type_building": ["广府", "宗祠", "合族祠", "书院"],
            "urban_cultural_position": ["沙面", "珠江新城"],
            "cross_cultural_decorative_observation": ["中西", "西方", "玻璃", "铸铁", "天使"],
            "cross_regional_building": ["晋祠", "山西", "岭南"],
            "cross_type_decorative_observation": ["开平", "碉楼", "岭南"],
        }.get(card.get("comparison_level"), [])
    )
    return [str(label).strip() for label in labels if str(label).strip()]


def comparison_context(
    user_query: str,
    *,
    audience: Literal["general", "research"] = "general",
    limit: int = 3,
) -> dict[str, Any]:
    """Return comparison guidance with claim-strength gates applied.

    General visitors receive only confirmed/cautious cards.  A question that
    explicitly asks for research material (or requests the ``research``
    audience) may receive research-only cards, always labelled as such.
    """
    if not _is_comparison_question(user_query):
        return {"status": "not_a_comparison_question", "cards": []}

    research_mode = audience == "research" or _is_research_question(user_query)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for card in load_comparison_cards().values():
        strength = card.get("claim_strength")
        if not research_mode and strength not in GENERAL_ALLOWED_STRENGTHS:
            continue
        query = user_query.casefold()
        matched_labels = [label for label in _card_labels(card) if label.casefold() in query]
        if not matched_labels:
            continue
        candidates.append((max(len(label) for label in matched_labels), card))

    candidates.sort(key=lambda item: (-item[0], item[1]["comparison_id"]))
    cards = []
    for _, card in candidates[:limit]:
        cards.append(
            {
                "comparison_id": card["comparison_id"],
                "theme_zh": card.get("theme_zh"),
                "comparison_level": card.get("comparison_level"),
                "claim_strength": card.get("claim_strength"),
                "visitor_conclusion_zh": card.get("visitor_conclusion_zh"),
                "on_site_observation_prompt": card.get("on_site_observation_prompt"),
                "source_refs": card.get("source_refs", []),
                "limitations_zh": card.get("limitations_zh"),
            }
        )

    if cards:
        return {
            "status": "ok_research_only" if research_mode else "ok",
            "cards": cards,
            "must_attribute": research_mode,
            "instruction": (
                "比较结论仅作研究线索，回答时须说明“有研究认为”，并保留适用范围；"
                "不得将其改写为景点评级或无来源的绝对事实。"
                if research_mode
                else "仅可按卡片的 claim_strength 与 limitations_zh 使用。",
            ),
        }

    if not research_mode:
        return {
            "status": "no_general_safe_card",
            "cards": [],
            "instruction": "当前匹配卡均为 research_only；请用本地 RAG 证据回答，或改为研究型比较提问。",
        }
    return {"status": "no_matching_card", "cards": []}


def format_comparison_hint(user_query: str, *, audience: Literal["general", "research"] = "general") -> str:
    """Create a compact prompt hint for a future guide-writing node."""
    context = comparison_context(user_query, audience=audience)
    if not context["cards"]:
        return ""
    lines = [context["instruction"]]
    for card in context["cards"]:
        lines.append(
            f"[{card['comparison_id']}] {card['theme_zh']}；"
            f"游客结论：{card['visitor_conclusion_zh']}；"
            f"来源：{', '.join(card['source_refs'])}；"
            f"边界：{card['limitations_zh']}"
        )
    return "\n".join(lines)
