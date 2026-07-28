"""Retrieve reviewed comparison cards without turning them into facts.

Comparison cards are guide-writing context, not a replacement for local RAG
evidence.  In particular, cards marked ``research_only`` may only be surfaced
for research-oriented questions and must retain their attribution boundary.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal

import yaml

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry


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


def is_explicit_comparison_question(query: str) -> bool:
    """Public D4 classifier; an unresolved pronoun is still a comparison."""
    return _is_comparison_question(query) or "它们" in query


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


def _gated_comparison_cards(registry: dict[str, KnowledgeCard]) -> list[KnowledgeCard]:
    return [
        card for card in registry.values()
        if card.card_type == "comparison"
        and card.runtime_status in {"enabled", "attributed_only"}
        and "attributed_comparison" in card.allowed_capabilities
    ]


def _matched_objects(card: KnowledgeCard, query: str) -> list[str]:
    """Return comparison objects whose own reviewed label is named in query.

    A comparison card is only safe when both of its actual objects are named.
    Theme and dimension labels may help a human browse cards, but must never
    turn a one-sided craft match into a two-object comparison.
    """
    normalized = query.casefold()
    objects = [
        str(value).strip()
        for value in card.raw_payload.get("comparison_objects", [])
        if isinstance(value, str) and value.strip()
    ]
    return [value for value in objects if _object_matches_query(value, normalized)]


def _object_aliases(object_name: str) -> tuple[str, ...]:
    """Return conservative deterministic aliases for reviewed object labels."""
    aliases = {object_name}
    # Parenthetical scope is not part of the visitor's object wording.
    aliases.add(object_name.split("（", 1)[0].strip())
    aliases.add(object_name.split("(", 1)[0].strip())
    aliases.update(
        {
            "陈氏书院": "陈家祠",
            "广州灰塑（含陈家祠案例）": "广州灰塑",
            "山东鄄城砖塑": "鄄城砖塑",
        }.get(object_name, "").split("\n")
    )
    # These are reviewed craft names, not a semantic expansion: they only
    # normalize the card's own Guangzhou-grey-plaster wording.
    if object_name.startswith("广州灰塑"):
        aliases.update({"陈家祠灰塑", "灰塑"})
    return tuple(alias for alias in aliases if alias)


def _object_matches_query(object_name: str, normalized_query: str) -> bool:
    return any(alias.casefold() in normalized_query for alias in _object_aliases(object_name))


def extract_comparison_subjects(user_query: str) -> tuple[str, ...]:
    """Extract only explicit public comparison subjects for base-RAG fallback.

    This list is deliberately small and deterministic.  It does not invent a
    counterpart when the visitor names only one side of a comparison.
    """
    public_terms = (
        "灰塑", "木雕", "砖雕", "砖塑", "陶塑", "石雕", "屋脊",
        "月台", "陈家祠", "陈氏书院", "晋祠", "开平碉楼",
    )
    return tuple(term for term in public_terms if term in user_query)


def retrieve_gated_comparison(
    user_query: str,
    *,
    allow_research: bool,
    registry_loader: Callable[[], dict[str, KnowledgeCard]] = build_registry,
) -> dict[str, Any]:
    """Return one D1-gated research comparison card or a safe status.

    The function intentionally returns no raw payload and never claims that a
    card's comparison objects are visible at the visitor's current position.
    """
    if not is_explicit_comparison_question(user_query):
        return {"status": "not_comparison_question", "card": None}
    if "它们" in user_query and not any(token in user_query for token in ("灰塑", "砖雕", "石雕", "木雕", "陶塑", "陈家祠", "陈氏书院", "月台", "屋脊")):
        return {"status": "ambiguous_objects", "card": None}
    try:
        cards = _gated_comparison_cards(registry_loader())
    except Exception:
        return {"status": "registry_unavailable", "card": None}
    ranked: list[KnowledgeCard] = []
    for card in cards:
        matched = _matched_objects(card, user_query)
        objects = [
            str(value).strip()
            for value in card.raw_payload.get("comparison_objects", [])
            if isinstance(value, str) and value.strip()
        ]
        # Exact card use requires every reviewed comparison object.  A theme,
        # a dimension, or a single craft can never fill in a missing side.
        if len(objects) >= 2 and len(matched) == len(objects):
            ranked.append(card)
    ranked.sort(key=lambda card: card.card_id)
    if not ranked:
        return {"status": "no_matching_card", "card": None}
    if not allow_research:
        return {"status": "research_card_not_permitted", "card": None}
    card = ranked[0]
    raw = card.raw_payload
    return {
        "status": "ok",
        "card": {
            "objects": list(raw.get("comparison_objects", [])),
            "scope_zh": raw.get("scope_zh"),
            "dimensions": list(raw.get("dimensions", [])),
            "similarities_zh": list(raw.get("similarities_zh", [])),
            "differences_zh": list(raw.get("differences_zh", [])),
            "claim_strength": raw.get("claim_strength"),
            "limitations_zh": raw.get("limitations_zh"),
            "on_site_observation_prompt": raw.get("on_site_observation_prompt"),
            "runtime_status": card.runtime_status,
        },
    }


def format_gated_comparison_answer(context: dict[str, Any]) -> str:
    """Render one attributed comparison without visitor-facing internal IDs."""
    status, card = context.get("status"), context.get("card")
    if status == "ambiguous_objects":
        return "您说的“它们”缺少可核对的两个比较对象；请直接说出两种工艺或两处建筑名称。"
    if status == "research_card_not_permitted":
        return "这类比较卡仅限明确研究视角或研学/专业模式使用；我可以先依据基础资料做不带论文结论的比较。"
    if status != "ok" or not card:
        return "暂未找到可安全引用的研究比较卡；我将仅依据基础资料处理，证据不足处不会强行比较。"
    dimensions = "、".join(str(item) for item in card.get("dimensions", [])[:3])
    lines = [f"相关研究以{card.get('scope_zh')}为比较范围，可从{dimensions or '材料、题材和视觉效果'}几个维度理解："]
    similarities = [str(item) for item in card.get("similarities_zh", []) if item]
    differences = [str(item) for item in card.get("differences_zh", []) if item]
    if similarities:
        lines.append(f"相同点：{'；'.join(similarities[:2])}")
    if differences:
        lines.append(f"主要差异：{'；'.join(differences[:3])}")
    if card.get("limitations_zh"):
        lines.append(f"适用范围与限制：{card['limitations_zh']}")
    if card.get("on_site_observation_prompt"):
        lines.append(f"观察建议：{card['on_site_observation_prompt']}（这只是观察建议，不表示对照对象就在当前点位可见。）")
    return "\n".join(lines)


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
