"""A2 point-aware RAG orchestration without changing tour progress.

This module does not implement retrieval itself.  It prepares a query for the
existing RAG tool, formats only the evidence returned by that tool, and restores
the A1 presentation context for an active tour.
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from route_planner import CATALOG_FILE, _read_catalog
from tour_intent import resolve_reviewed_node
from tour_presenter import present_tour_state


GUIDE_CARDS_FILE = Path("data/chen_clan_academy/routes/node_guide_cards_v1.json")
MARKERS_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")


@lru_cache(maxsize=1)
def _guide_cards() -> dict[str, dict[str, Any]]:
    with GUIDE_CARDS_FILE.open(encoding="utf-8") as handle:
        return {card["node_id"]: card for card in json.load(handle)["cards"]}


@lru_cache(maxsize=1)
def _marker_names() -> dict[str, str]:
    with MARKERS_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["node_id"]: row["name"]
            for row in csv.DictReader(handle)
            if row.get("node_id") and row.get("name")
        }


def current_stop_context(tour_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return reviewed point metadata as retrieval guidance, never as evidence."""
    if not tour_state or not tour_state.get("current_stop_id"):
        return None
    node_id = tour_state["current_stop_id"]
    card = _guide_cards().get(node_id, {})
    catalog = _read_catalog(CATALOG_FILE).get(node_id, {})
    name = card.get("display_name") or catalog.get("stop_name") or _marker_names().get(node_id, node_id)
    return {
        "node_id": node_id,
        "name": name,
        "guide_focus": card.get("guide_focus") or catalog.get("guide_focus"),
        # Candidate names are only search hints.  The final response must still
        # cite returned RAG evidence instead of treating this mapping as proof.
        "candidate_ornament_names": [
            item["name"] for item in card.get("ornaments", []) if item.get("name")
        ],
        "card": card or None,
    }


def resolve_point_context(user_query: str, tour_state: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve an explicit reviewed point, or use the real current position.

    Returns ``(context, error_code)``.  An unrecognised location-like phrase is
    rejected rather than silently being treated as the current point.
    """
    resolution = resolve_reviewed_node(user_query)
    if resolution.node_id:
        node_id = resolution.node_id
        card = _guide_cards().get(node_id, {})
        catalog = _read_catalog(CATALOG_FILE).get(node_id, {})
        return {
            "node_id": node_id,
            "name": card.get("display_name") or catalog.get("stop_name") or _marker_names().get(node_id, node_id),
            "guide_focus": card.get("guide_focus") or catalog.get("guide_focus"),
            "candidate_ornament_names": [item["name"] for item in card.get("ornaments", []) if item.get("name")],
            "card": card or None,
        }, None
    if resolution.reason_code in {"ambiguous_node_name", "multiple_node_mentions"}:
        return None, resolution.reason_code
    if any(token in user_query for token in ("这里", "当前点", "当前站", "本点")):
        context = current_stop_context(tour_state)
        return (context, None) if context else (None, "current_point_unavailable")
    # A location-like noun plus an inventory question should not be guessed.
    if any(token in user_query for token in ("厅", "庭", "台", "院", "门", "廊", "园")):
        return None, "unknown_point"
    return None, None


def is_point_inventory_request(user_query: str, tour_state: dict[str, Any] | None = None) -> bool:
    """Recognize only deterministic 'what is at this point' inventory requests."""
    inventory_terms = ("这里有什么", "当前点", "当前站", "本点", "哪些装饰", "有哪些装饰", "主要看什么", "有什么值得看")
    if any(term in user_query for term in inventory_terms):
        return True
    resolution = resolve_reviewed_node(user_query)
    return bool(resolution.node_id and any(term in user_query for term in ("有什么", "哪些", "主要看")))


def format_point_inventory(
    user_query: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return an audited association list without treating it as RAG evidence."""
    context, error_code = resolve_point_context(user_query, tour_state)
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if error_code:
        messages = {
            "ambiguous_node_name": "该名称对应多个已审核点位，请补充方位后再查询。",
            "multiple_node_mentions": "您同时提到了多个点位，请一次查询一个明确点位。",
            "current_point_unavailable": "当前没有可用的导览位置，请先到达一个已审核点位或直接说出地图上的点位名称。",
            "unknown_point": "未找到该点位对应的已审核空间节点，因此不会猜测其文物清单。",
        }
        return {
            "message": messages[error_code], "inventory": None, "point_context": None,
            "presentation": {**presentation, "message": messages[error_code], "code": error_code, "ok": False} if presentation else None,
            "mode": "inventory_error",
        }
    if not context:
        return {"message": "这不是可识别的点位清单问题，将按普通事实检索处理。", "inventory": None, "point_context": None, "presentation": None, "mode": "not_inventory"}
    card = context.get("card")
    if not card:
        message = f"{context['name']} 已是审核空间点位，但当前点位讲解包缺失；我不能据此猜测文物清单。"
        return {
            "message": message, "inventory": None, "point_context": context,
            "presentation": {**presentation, "message": message, "code": "point_card_missing", "ok": False} if presentation else None,
            "mode": "inventory_missing_card",
        }
    ornaments = [
        {"ornament_id": item["ornament_id"], "name": item["name"], "craft": item["craft"]}
        for item in card.get("ornaments", [])
    ]
    craft_distribution = card.get("craft_distribution", {})
    names = "、".join(item["name"] for item in ornaments)
    craft_text = "；".join(f"{craft} {count} 件" for craft, count in craft_distribution.items())
    message = (
        f"{context['name']} 的已审核点位清单共有 {len(ornaments)} 件关联文物。\n"
        f"导览关注：{context.get('guide_focus') or '待补充'}。\n"
        f"工艺分布：{craft_text or '待补充'}。\n"
        f"关联文物：{names or '暂无'}。\n"
        "以上是人工审核的“文物—点位”关联清单；如需了解某件文物的工艺、寓意或故事，我会再调用基础 RAG 并给出来源。"
    )
    return {
        "message": message,
        "inventory": {"node_id": context["node_id"], "ornaments": ornaments, "craft_distribution": craft_distribution, "guide_focus": context.get("guide_focus")},
        "point_context": context,
        "presentation": {**presentation, "message": message, "code": "point_inventory", "ok": True} if presentation else None,
        "mode": "inventory",
    }


def build_tour_qa_query(user_query: str, tour_state: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
    """Augment one factual question with the active position's reviewed hints."""
    context, _ = resolve_point_context(user_query, tour_state)
    context = context or current_stop_context(tour_state)
    if not context:
        return user_query, None
    card = context.get("card") or {}
    detail_craft = next((craft for craft in ("石雕", "灰塑", "木雕", "砖雕", "陶塑", "铜铁铸") if craft in user_query), None)
    candidate_items = card.get("ornaments", [])
    if detail_craft:
        candidate_items = [item for item in candidate_items if detail_craft in item.get("craft", "")]
    candidates = "、".join(item["name"] for item in candidate_items[:6] if item.get("name"))
    hints = [f"当前导览点位提示：{context['name']}（{context['node_id']}）"]
    if context.get("guide_focus"):
        hints.append(f"讲解关注方向：{context['guide_focus']}")
    if candidates:
        hints.append(f"可用于检索的已审核名称提示：{candidates}")
    hints.append("以上点位信息只用于检索提示；回答中的事实必须由检索 evidence 支持。")
    return f"用户问题：{user_query}\n" + "\n".join(hints), context


def parse_rag_payload(raw: str) -> dict[str, Any]:
    """Normalize the existing tool's JSON response into a safe payload."""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"evidence": [], "error": "本地知识检索返回格式无效。"}
    evidence = payload.get("evidence")
    return {**payload, "evidence": evidence if isinstance(evidence, list) else []}


def _evidence_line(item: dict[str, Any]) -> str:
    title_path = item.get("title_path") or []
    title = " / ".join(title_path[-2:]) if isinstance(title_path, list) and title_path else item.get("document", "资料条目")
    source_ids = "、".join(item.get("source_ids") or []) or "未标注来源编号"
    content = " ".join(str(item.get("content") or "").split())
    excerpt = content[:180] + ("…" if len(content) > 180 else "")
    document = item.get("document") or "未标注文档"
    return f"- {document} / {title}（来源：{source_ids}）：{excerpt}"


def format_tour_qa_answer(
    user_query: str,
    payload: dict[str, Any],
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Format RAG evidence plus an unchanged A1 guide context as one response."""
    evidence = payload.get("evidence") or []
    context = current_stop_context(tour_state)
    if evidence:
        answer = "根据本地知识库检索到的资料：\n" + "\n".join(
            _evidence_line(item) for item in evidence[:3] if isinstance(item, dict)
        )
    else:
        detail = payload.get("error") or "当前本地知识库没有检索到足以支持该问题的资料。"
        answer = f"资料不足：{detail} 我不会根据当前点位补造事实。"

    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if presentation:
        point_name = context["name"] if context else "当前导览位置"
        phase = interaction_state.get("stop_phase")
        answer += f"\n\n导览上下文：您当前位于{point_name}，阶段为 {phase}。"
        answer += " 可继续使用下方现有导览操作；本次问答未改变路线进度。"
        presentation = {
            **presentation,
            "message": answer,
            "code": "tour_qa_answer" if evidence else "tour_qa_no_evidence",
            "ok": True,
            "evidence_count": len(evidence),
        }
    return {
        "message": answer,
        "evidence": evidence,
        "point_context": context,
        "presentation": presentation,
    }


def answer_tour_question(
    user_query: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
) -> dict[str, Any]:
    """Use one injected existing RAG callable and leave both state snapshots untouched."""
    if is_point_inventory_request(user_query, tour_state):
        return {**format_point_inventory(user_query, tour_state, interaction_state), "retrieval_query": None, "evidence": []}
    retrieval_query, context = build_tour_qa_query(user_query, tour_state)
    try:
        payload = parse_rag_payload(rag_search(retrieval_query))
    except Exception as exc:  # The adapter must never let retrieval break a tour.
        payload = {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}
    result = format_tour_qa_answer(user_query, payload, tour_state, interaction_state)
    return {**result, "retrieval_query": retrieval_query, "point_context": context}
