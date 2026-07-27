"""D2 deterministic, eligibility-gated terminology answers for ``tour_qa``.

This adapter intentionally does not read glossary YAML itself.  D1's registry
is the only source of runnable cards; :mod:`glossary_retrieval` is reused only
for reviewed point-to-term association ordering.
"""

from __future__ import annotations

from typing import Any, Callable

from glossary_retrieval import point_glossary_context
from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry
from tour_presenter import present_tour_state


COMPARISON_TERMS = ("区别", "不同", "比较", "对比", "vs", "VS")
ENGLISH_TERMS = ("英文怎么说", "英语怎么说", "英文", "英语")
PINYIN_TERMS = ("拼音",)
DOMAIN_TERMS = ("属于什么工艺", "属于什么构件", "什么领域", "属于什么领域")
ALIAS_TERMS = ("英文别名", "英文别称", "英文名称", "别名", "别称")
DEFINITION_TERMS = ("是什么", "指什么", "定义", "含义")


def _labels(card: KnowledgeCard) -> tuple[str, ...]:
    raw = card.raw_payload
    values = [raw.get("zh"), *(raw.get("aliases_zh") or ()), *(raw.get("aliases_en") or ())]
    return tuple(str(value) for value in values if isinstance(value, str) and value.strip())


def _question_kind(query: str) -> str | None:
    if any(token in query for token in COMPARISON_TERMS):
        return None
    if any(token in query for token in ALIAS_TERMS):
        return "aliases"
    if any(token in query for token in ENGLISH_TERMS):
        return "english"
    if any(token in query for token in PINYIN_TERMS):
        return "pinyin"
    if any(token in query for token in DOMAIN_TERMS):
        return "domain"
    if any(token in query for token in DEFINITION_TERMS):
        return "definition"
    return None


def _term_cards(registry: dict[str, KnowledgeCard]) -> list[KnowledgeCard]:
    return [card for card in registry.values() if card.card_type == "glossary_term" and card.visitor_visible]


def _matched_cards(query: str, registry: dict[str, KnowledgeCard]) -> list[KnowledgeCard]:
    matches = [card for card in _term_cards(registry) if any(label.casefold() in query.casefold() for label in _labels(card))]
    return sorted(matches, key=lambda card: (-(max((len(label) for label in _labels(card) if label.casefold() in query.casefold()), default=0)), card.card_id))


def is_explicit_term_question(user_query: str) -> bool:
    """Return whether text is a controlled terminology question.

    This deliberately checks the D1 registry so a route router cannot mistake
    arbitrary ``X 是什么`` text for a glossary request.
    """
    if not _question_kind(user_query):
        return False
    try:
        return bool(_matched_cards(user_query, build_registry()))
    except Exception:
        return False


def rank_term_candidates(
    user_query: str,
    registry: dict[str, KnowledgeCard],
    *,
    associated_ids: set[str] | None = None,
) -> list[KnowledgeCard]:
    """Apply association ordering only after deterministic text matching.

    The returned order is a retrieval hint.  It is not a statement that the
    visitor can currently see a term's corresponding object.
    """
    associated_ids = associated_ids or set()
    matches = _matched_cards(user_query, registry)
    return sorted(matches, key=lambda card: (card.card_id not in associated_ids, card.card_id))


def _sources(card: KnowledgeCard) -> str:
    return "、".join(card.source_refs) or "未标注来源编号"


def _presentation_message(message: str, tour_state: dict[str, Any] | None, interaction_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not (tour_state and interaction_state):
        return None
    presentation = present_tour_state(tour_state, interaction_state)
    return {**presentation, "message": message, "code": "term_card_answer", "ok": True}


def answer_term_question(
    user_query: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    *,
    registry_loader: Callable[[], dict[str, KnowledgeCard]] = build_registry,
    association_reader: Callable[[str | None, str], dict[str, Any]] = point_glossary_context,
) -> dict[str, Any] | None:
    """Answer one explicit, eligible terminology query or return ``None``.

    ``None`` deliberately means that callers should use their existing base
    RAG path.  Returned values never modify tour state and never reveal a
    disabled card's draft translation.
    """
    kind = _question_kind(user_query)
    if not kind:
        return None
    try:
        registry = registry_loader()
    except Exception:
        return None
    candidates = _matched_cards(user_query, registry)
    if not candidates:
        return None

    current_node = (tour_state or {}).get("current_stop_id")
    try:
        associated_ids = {item.get("term_id") for item in association_reader(current_node, user_query).get("terms", [])}
    except Exception:
        associated_ids = set()
    candidates = rank_term_candidates(user_query, registry, associated_ids=associated_ids)

    enabled = [card for card in candidates if card.runtime_status == "enabled"]
    if not enabled:
        # A draft English translation must never be handed to a later model.
        if kind == "english":
            message = "该术语当前尚未通过英文输出审核，因此我不能提供英文译法。"
            return {
                "message": message, "mode": "term_card_unavailable", "term": None, "evidence": [],
                "presentation": _presentation_message(message, tour_state, interaction_state),
            }
        return None
    if len(enabled) > 1:
        labels = "、".join(card.raw_payload.get("zh", card.card_id) for card in enabled[:4])
        message = f"您提到的术语可能对应多个已审核条目（{labels}），请补充完整术语后我再说明。"
        return {
            "message": message, "mode": "term_card_clarification", "term": None, "evidence": [],
            "presentation": _presentation_message(message, tour_state, interaction_state),
        }

    card = enabled[0]
    raw = card.raw_payload
    capabilities = set(card.allowed_capabilities)
    zh = raw.get("zh") or card.card_id
    source_text = _sources(card)
    if kind == "english":
        if "en_translation" not in capabilities or not raw.get("en"):
            message = f"“{zh}”当前没有可输出的已审核英文译法。"
        else:
            aliases = [item for item in raw.get("aliases_en", []) if isinstance(item, str) and item]
            suffix = f"；已审核英文别名包括 {', '.join(aliases)}" if aliases else ""
            message = f"“{zh}”常用英文为 {raw['en']}{suffix}（来源：{source_text}）。"
    elif kind == "pinyin":
        if "pinyin" not in capabilities or not raw.get("pinyin"):
            message = f"“{zh}”当前没有可输出的已审核拼音。"
        else:
            message = f"“{zh}”的拼音为 {raw['pinyin']}（来源：{source_text}）。"
    elif kind == "domain":
        if not raw.get("domain"):
            return None
        domain_labels = {
            "architectural_components": "建筑构件",
            "decorative_crafts": "装饰工艺",
            "sculptural_techniques": "雕刻技法",
            "materials": "材料",
            "heritage_protection": "文物保护",
        }
        domain = domain_labels.get(str(raw["domain"]), str(raw["domain"]))
        message = f"“{zh}”在术语卡中归入{domain}领域（来源：{source_text}）。"
    elif kind == "aliases":
        if "en_translation" not in capabilities:
            message = f"“{zh}”当前没有可输出的已审核英文别名。"
        else:
            aliases = [raw.get("en"), *(raw.get("aliases_en") or ())]
            aliases = [item for item in aliases if isinstance(item, str) and item]
            message = f"“{zh}”的已审核英文名称为 {', '.join(dict.fromkeys(aliases)) or '暂无'}（来源：{source_text}）。"
    else:
        if "definition_zh" not in capabilities or not raw.get("short_definition_zh"):
            return None
        message = f"“{zh}”是{raw['short_definition_zh']}（来源：{source_text}）。"

    if card.card_id in associated_ids and current_node:
        message += " 您当前所在点位与该术语存在审核关联；是否能清楚看到仍以现场为准。"
    if tour_state and interaction_state:
        message += "\n\n本次术语说明未改变路线进度，您可继续使用现有导览操作。"
    return {
        "message": message,
        "mode": "term_card",
        "term": {"card_id": card.card_id, "zh": zh, "source_ids": list(card.source_refs)},
        "evidence": [],
        "presentation": _presentation_message(message, tour_state, interaction_state),
    }
