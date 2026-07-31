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
from glossary_retrieval import format_point_glossary_hint, point_glossary_context
from comparison_retrieval import (
    extract_comparison_subjects,
    format_gated_comparison_answer,
    is_explicit_comparison_question,
    retrieve_gated_comparison,
)
from research_card_retrieval import format_research_answer, is_explicit_research_question, retrieve_research_cards
from term_card_runtime import (
    answer_term_question,
    is_explicit_term_question,
    runtime_term_instance_enhancement,
)
from photo_spot_runtime import answer_photo_request, is_explicit_photo_request
from visit_safety_rules import answer_visit_safety_question
from qa_context import create_qa_context, is_qa_follow_up_detail_request, validate_qa_context
from tour_intent import resolve_reviewed_node
from tour_presenter import present_tour_state
from craft_knowledge import (
    CRAFT_TERMS,
    CraftExplanationRequest,
    CraftKnowledgeError,
    load_craft_record,
    parse_craft_explanation_request,
    parse_craft_location_request,
    render_craft_explanation,
    render_craft_location_answer,
)
from single_fact_answer import (
    identify_single_fact_kind,
    render_single_fact_answer,
    single_fact_categories_for_kind,
)
from controlled_knowledge_query import ControlledKnowledgePlan
from ornament_detail_runtime import (
    build_object_evidence_view,
    filter_object_evidence,
    render_object_detail,
)
from ornament_clarification import (
    create_pending_ornament_clarification,
    load_pending_ornament_clarification,
    resolve_pending_ornament_choice,
)


GUIDE_CARDS_FILE = Path("data/chen_clan_academy/routes/node_guide_cards_v1.json")
MARKERS_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")
DEICTIC_POINT_TERMS = ("这里", "此处", "眼前", "当前点", "当前站", "本点")
FEATURE_TERMS = ("特点", "特征", "工艺", "怎么做", "有什么")
TERM_EXPLANATION_TERMS = ("是什么", "什么意思", "指什么", "怎么理解")
OBJECT_DETAIL_TERMS = ("讲讲", "介绍", "说说", "详细", "故事", "人物", "画面", "寓意", "是什么", "什么意思", "特点")
REVIEWED_ORNAMENT_CRAFTS = frozenset({"灰塑", "木雕", "石雕", "陶塑", "砖雕", "铜铁铸", "壁画", "砖雕&铜铁铸&壁画"})
CRAFT_ONLY_SCOPE_MARKERS = ("只根据", "仅根据")
@lru_cache(maxsize=1)
def load_guide_cards() -> dict[str, dict[str, Any]]:
    """Load reviewed point guide cards for A2 and later guide-program stages."""
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
    return point_context_for_node(tour_state["current_stop_id"])


def point_context_for_node(node_id: str) -> dict[str, Any]:
    """Return reviewed metadata for one node; never infer physical location."""
    card = load_guide_cards().get(node_id, {})
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
        "glossary_context": point_glossary_context(node_id),
        "card": card or None,
    }


def resolve_point_context(user_query: str, tour_state: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve an explicit reviewed point, or use the real current position.

    Returns ``(context, error_code)``.  An unrecognised location-like phrase is
    rejected rather than silently being treated as the current point.
    """
    resolution = resolve_reviewed_node(user_query)
    if resolution.node_id:
        return point_context_for_node(resolution.node_id), None
    if resolution.reason_code in {"ambiguous_node_name", "multiple_node_mentions"}:
        return None, resolution.reason_code
    if any(token in user_query for token in DEICTIC_POINT_TERMS):
        context = current_stop_context(tour_state)
        return (context, None) if context else (None, "current_point_unavailable")
    # A location-like noun plus an inventory question should not be guessed.
    if any(token in user_query for token in ("厅", "庭", "台", "院", "门", "廊", "园")):
        return None, "unknown_point"
    return None, None


def is_point_inventory_request(user_query: str, tour_state: dict[str, Any] | None = None) -> bool:
    """Recognize only deterministic 'what is at this point' inventory requests."""
    inventory_terms = (
        "这里有什么", "这里呢", "此处呢", "眼前呢", "当前点", "当前站", "本点",
        "哪些装饰", "有哪些装饰", "主要看什么", "有什么值得看",
        "能看到什么", "可以看到什么",
    )
    if any(term in user_query for term in inventory_terms):
        return True
    resolution = resolve_reviewed_node(user_query)
    return bool(
        resolution.node_id
        and any(term in user_query for term in ("有什么", "哪些", "主要看", "讲讲", "介绍", "说说"))
    )


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
    glossary_context = point_glossary_context(context["node_id"], user_query)
    glossary_terms = glossary_context.get("terms", [])
    glossary_text = "、".join(item["zh"] for item in glossary_terms[:8] if item.get("zh"))
    message = (
        f"{context['name']} 的已审核点位清单共有 {len(ornaments)} 件关联文物。\n"
        f"导览关注：{context.get('guide_focus') or '待补充'}。\n"
        f"工艺分布：{craft_text or '待补充'}。\n"
        f"关联文物：{names or '暂无'}。\n"
        "以上是人工审核的“文物—点位”关联清单；如需了解某件文物的工艺、寓意或故事，我会再调用基础 RAG 并给出来源。"
    )
    if glossary_text:
        message += f"\n本点可继续追问的专业术语：{glossary_text}。"
    return {
        "message": message,
        "inventory": {"node_id": context["node_id"], "ornaments": ornaments, "craft_distribution": craft_distribution, "guide_focus": context.get("guide_focus"), "glossary_terms": glossary_terms},
        "point_context": context,
        "presentation": {**presentation, "message": message, "code": "point_inventory", "ok": True} if presentation else None,
        "mode": "inventory",
    }


def _reviewed_ornament_matches(user_query: str, context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return only exact reviewed name matches, never model-guessed objects."""
    cards = load_guide_cards()
    scoped_cards = [context.get("card")] if context and context.get("card") else list(cards.values())
    matches: list[dict[str, Any]] = []
    for card in scoped_cards:
        if not isinstance(card, dict):
            continue
        for ornament in card.get("ornaments", []):
            if not isinstance(ornament, dict):
                continue
            name = ornament.get("name")
            if isinstance(name, str) and name and name in user_query:
                matches.append({**ornament, "node_id": card.get("node_id"), "point_name": card.get("display_name")})
    explicit_crafts = [craft for craft in CRAFT_TERMS if craft in user_query]
    if len(explicit_crafts) == 1:
        matches = [item for item in matches if item.get("craft") == explicit_crafts[0]]
    return matches


def _object_detail_request(user_query: str) -> bool:
    return any(term in user_query for term in OBJECT_DETAIL_TERMS)


def _resolve_ornament_detail_request(
    user_query: str,
    tour_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a reviewed object within an explicit point before inventory routing."""
    if not _object_detail_request(user_query):
        return None
    context, point_error = resolve_point_context(user_query, tour_state)
    if point_error in {"ambiguous_node_name", "multiple_node_mentions", "unknown_point"}:
        return None
    matches = _reviewed_ornament_matches(user_query, context)
    if not matches:
        # A named reviewed point plus a different *known* object must not fall
        # into inventory.  A broad “讲讲月台” contains no object name and must
        # retain the existing point overview behaviour.
        global_matches = _reviewed_ornament_matches(user_query, None)
        if context and global_matches:
            return {
                "status": "unmatched_at_point",
                "context": context,
                "item": None,
            }
        return None
    unique = {(item.get("node_id"), item.get("ornament_id")) for item in matches}
    if len(unique) != 1:
        return {"status": "ambiguous", "context": context, "item": None, "matches": matches}
    item = matches[0]
    return {"status": "ok", "context": context or point_context_for_node(item["node_id"]), "item": item}


def _candidate_categories_for_ambiguous_ornaments(
    resolved: dict[str, Any],
) -> list[dict[str, Any]]:
    """Group only publicly indistinguishable audited matches for clarification."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for item in resolved.get("matches", []):
        node_id = str(item.get("node_id") or "")
        name = str(item.get("name") or "")
        craft = str(item.get("craft") or "")
        raw_location = str(item.get("raw_location") or "")
        if not all((node_id, name, craft)):
            continue
        if item.get("final_node_id") not in {None, node_id}:
            continue
        if item.get("mapping_decision") not in {None, "change", "add_node"}:
            continue
        groups.setdefault((name, craft, node_id, raw_location), []).append(item)
    candidates: list[dict[str, Any]] = []
    for key, members in sorted(groups.items(), key=lambda entry: min(str(item.get("ornament_id")) for item in entry[1])):
        name, craft, node_id, raw_location = key
        node_name = str(members[0].get("point_name") or point_context_for_node(node_id)["name"])
        member_ids = sorted(str(item["ornament_id"]) for item in members if item.get("ornament_id"))
        if len(member_ids) == 1:
            candidates.append({
                "candidate_kind": "exact_object",
                "display_name": name,
                "craft": craft,
                "node_id": node_id,
                "node_name": node_name,
                "raw_location": raw_location or None,
                "summary": f"审核对象记录显示其属于{craft}装饰。",
                "source_ids": [],
                "ornament_id": member_ids[0],
                "selectable_for_exact_detail": True,
            })
        else:
            candidates.append({
                "candidate_kind": "ambiguous_group",
                "display_name": name,
                "craft": craft,
                "node_id": node_id,
                "node_name": node_name,
                "raw_location": raw_location or None,
                "summary": f"审核对象记录显示其属于{craft}装饰。",
                "source_ids": [],
                "member_ornament_ids": member_ids,
                "selectable_for_exact_detail": False,
                "blocked_reason": "indistinguishable_reviewed_entities",
            })
    for index, candidate in enumerate(candidates, start=1):
        candidate["choice_index"] = index
    return candidates


def _render_ornament_candidate_clarification(
    subject_name: str,
    candidates: list[dict[str, Any]],
) -> str:
    lines = [f"“{subject_name}”对应多个审核对象，请先选择想了解的版本："]
    for candidate in candidates:
        location = candidate.get("raw_location")
        location_text = f"，审核关联位置为{location}" if location else ""
        lines.append(
            f"{candidate['choice_index']}. {candidate['craft']}《{candidate['display_name']}》"
            f"——{candidate['node_name']}{location_text}。{candidate['summary']}"
        )
    lines.append("请回复序号或工艺名称；如选择的数据仍无法可靠区分，我不会任选其中一条记录。")
    return "\n".join(lines)


def _reviewed_ornament_by_pending_choice(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Rehydrate one already-selected exact ID without another name ranking pass."""
    node_id = candidate.get("node_id")
    ornament_id = candidate.get("ornament_id")
    card = load_guide_cards().get(node_id) if isinstance(node_id, str) else None
    if not isinstance(card, dict) or not isinstance(ornament_id, str):
        return None
    for item in card.get("ornaments", []):
        if isinstance(item, dict) and item.get("ornament_id") == ornament_id:
            if item.get("name") != candidate.get("display_name") or item.get("craft") != candidate.get("craft"):
                return None
            return {**item, "node_id": node_id, "point_name": card.get("display_name")}
    return None


def _current_candidates_for_pending_subject(
    subject_name: str,
    original_query: str,
    tour_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Recompute candidates from the current registry in the original scope."""
    resolved = _resolve_ornament_detail_request(original_query, tour_state)
    if resolved and isinstance(resolved.get("matches"), list):
        matches = resolved["matches"]
    elif resolved and resolved.get("item"):
        matches = [resolved["item"]]
    else:
        matches = _reviewed_ornament_matches(subject_name, None)
    return _candidate_categories_for_ambiguous_ornaments({"matches": matches})


def _refresh_pending_ornament_choice(
    user_query: str,
    pending: dict[str, Any],
    tour_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a pending choice against the current registry, not its snapshot."""
    candidates = _current_candidates_for_pending_subject(
        pending["subject_name"], pending["original_query"], tour_state,
    )
    if not candidates:
        return {"status": "unavailable"}, pending
    if len(candidates) == 1:
        candidate = candidates[0]
        selected_by_craft = candidate["craft"] in user_query
        selected_by_point = candidate["node_name"] in user_query
        selected_by_index = user_query.strip() in {"1", "第一个", "第1个"}
        if selected_by_craft or selected_by_point or selected_by_index:
            if candidate["candidate_kind"] == "exact_object":
                return {"status": "selected", "candidate": candidate}, pending
            return {"status": "data_ambiguity", "candidate": candidate}, pending
        return {"status": "unresolved"}, pending
    refreshed = create_pending_ornament_clarification(
        original_query=pending["original_query"],
        subject_name=pending["subject_name"],
        candidates=candidates,
        requested_detail=pending["requested_detail"],
        evidence_scope=pending["evidence_scope"],
    )
    return resolve_pending_ornament_choice(user_query, refreshed), refreshed


def resolve_ornament_story_scope_request(
    user_query: str,
    tour_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve a narrow object-story request and its explicit proof scope.

    Object identity remains owned by ``_resolve_ornament_detail_request``.
    This helper only identifies when the visitor explicitly confines the answer
    to a craft overview, which cannot prove an individual object's story.
    """
    resolved = _resolve_ornament_detail_request(user_query, tour_state)
    if resolved is None:
        return None
    craft_only = (
        any(marker in user_query for marker in CRAFT_ONLY_SCOPE_MARKERS)
        and any(craft in user_query for craft in CRAFT_TERMS)
        and any(marker in user_query for marker in ("工艺", "资料", "总述"))
    )
    item = resolved.get("item") or {}
    if resolved.get("status") != "ok" or not item:
        return {
            "resolved": resolved,
            "requested_scope": "craft_only" if craft_only else "exact_ornament",
        }
    return {
        "resolved": resolved,
        "requested_scope": "craft_only" if craft_only else "exact_ornament",
        "requested_subject": item.get("name"),
    }


def _ornament_story_source_clarification(
    story_scope: dict[str, Any],
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed when craft-only material is asked to prove an object story."""
    subject = story_scope.get("requested_subject") or "该对象"
    message = (
        f"现有工艺总述只能说明相关工艺，无法证明“{subject}”的完整传说或人物情节。"
        f"如允许使用“{subject}”的审核对象资料，我可以再按该对象的已核验内容说明。"
    )
    presentation = (
        present_tour_state(tour_state, interaction_state)
        if tour_state and interaction_state
        else None
    )
    if presentation:
        presentation = {
            **presentation,
            "message": message,
            "code": "ornament_story_source_clarification",
            "ok": False,
            "evidence_count": 0,
        }
    return {
        "message": message,
        "mode": "ornament_story_source_clarification",
        "answer_mode": "ornament_story_source_clarification",
        "evidence": [],
        "source_ids": [],
        "point_context": story_scope["resolved"].get("context"),
        "presentation": presentation,
        "retrieval_query": None,
        "ornament_story_scope": {
            "requested_subject": subject,
            "requested_scope": "craft_only",
            "required_scope": "exact_ornament",
            "evidence_sufficient": False,
            "source_ids": [],
            "state_changed": False,
        },
    }


def _ornament_candidate_data_ambiguity(
    choice: dict[str, Any],
) -> dict[str, Any]:
    """Explain a blocked category without choosing an indistinguishable member."""
    candidate = choice["candidate"]
    name = candidate["display_name"]
    craft = candidate["craft"]
    message = (
        f"{candidate['node_name']}审核数据中有 {len(candidate['member_ornament_ids'])} 条名称、"
        f"工艺和公开位置都相同的{craft}《{name}》记录，现有资料暂时无法可靠区分具体对象。"
        "在审核关系确认前，我不能任选其中一条讲述。"
        "您可以先了解其他可唯一识别的版本，或等待对象关系完成核验。"
    )
    return {
        "message": message,
        "mode": "ornament_candidate_data_ambiguity",
        "answer_mode": "ornament_candidate_data_ambiguity",
        "evidence": [],
        "source_ids": [],
        "point_context": point_context_for_node(candidate["node_id"]),
        "presentation": None,
        "retrieval_query": None,
        "pending_ornament_clarification": choice["pending"],
        "ornament_candidate_audit": {
            "subject_name": choice["pending"]["subject_name"],
            "selected_craft": craft,
            "candidate_count": len(candidate["member_ornament_ids"]),
            "selectable": False,
            "blocked_reason": "indistinguishable_reviewed_entities",
            "member_ornament_ids": list(candidate["member_ornament_ids"]),
            "state_changed": False,
        },
    }


def _answer_pending_ornament_choice(
    user_query: str,
    pending_value: Any,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    visitor_profile: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Execute only a unique pending category selection, otherwise clarify."""
    pending = load_pending_ornament_clarification(pending_value)
    if pending is None:
        return None
    # A new named-object request supersedes the old pending choice instead of
    # being misread as an answer such as “that one”.
    new_request = _resolve_ornament_detail_request(user_query, tour_state)
    if new_request is not None and pending["subject_name"] not in user_query:
        return None
    # Pending candidate summaries are only a UI snapshot. Re-evaluate the
    # user's selection against the latest reviewed registry so data repairs
    # cannot be masked by a long-lived Studio thread.
    choice, refreshed_pending = _refresh_pending_ornament_choice(
        user_query, pending, tour_state,
    )
    if choice["status"] == "unavailable":
        return {
            "message": "该对象的审核候选资料已更新，当前没有可安全核验的对应对象；请重新说明想了解的对象。",
            "mode": "ornament_detail_unavailable",
            "evidence": [],
            "presentation": None,
            "retrieval_query": None,
            "pending_ornament_clarification": None,
        }
    if choice["status"] == "selected":
        item = _reviewed_ornament_by_pending_choice(choice["candidate"])
        if item is None:
            return {
                "message": "该候选的审核对象记录目前无法安全确认，请重新选择或稍后再试。",
                "mode": "ornament_detail_clarification",
                "evidence": [],
                "presentation": None,
                "retrieval_query": None,
                "pending_ornament_clarification": None,
            }
        resolved = {"status": "ok", "context": point_context_for_node(item["node_id"]), "item": item}
        if pending["evidence_scope"] == "craft_only":
            return {
                **_ornament_story_source_clarification(
                    {
                        "resolved": resolved,
                        "requested_subject": item["name"],
                        "requested_scope": "craft_only",
                    },
                    tour_state,
                    interaction_state,
                ),
                "pending_ornament_clarification": None,
            }
        return {
            **_answer_ornament_detail(
                resolved,
                tour_state,
                interaction_state,
                rag_search,
                detailed=pending["requested_detail"] == "story",
                story_detail=pending["requested_detail"] == "story",
                listen_only=(visitor_profile or {}).get("interaction_mode") == "listen_only",
            ),
            "pending_ornament_clarification": None,
        }
    if choice["status"] == "data_ambiguity":
        return _ornament_candidate_data_ambiguity(choice)
    if choice["status"] == "unresolved":
        message = _render_ornament_candidate_clarification(
            refreshed_pending["subject_name"], refreshed_pending["candidate_summaries"],
        )
        return {
            "message": message,
            "mode": "ornament_candidate_clarification",
            "evidence": [],
            "presentation": None,
            "retrieval_query": None,
            "pending_ornament_clarification": refreshed_pending,
            "ornament_candidates": refreshed_pending["candidate_summaries"],
        }
    return None


def _answer_ornament_detail(
    resolved: dict[str, Any],
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    detailed: bool = False,
    listen_only: bool = False,
    story_detail: bool = False,
) -> dict[str, Any]:
    """Answer one uniquely resolved audited object without changing tour state."""
    context = resolved.get("context")
    status = resolved.get("status")
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if status == "ambiguous":
        message = "该名称对应多个已审核对象，请补充所在点位或工艺后再讲解。"
        return {"message": message, "mode": "ornament_detail_clarification", "evidence": [], "point_context": context, "presentation": presentation, "retrieval_query": None}
    if status == "unmatched_at_point":
        message = f"该对象未在{context['name']}的已审核对象中匹配，因此不把其他点位对象当作本点内容。"
        return {"message": message, "mode": "ornament_detail_clarification", "evidence": [], "point_context": context, "presentation": presentation, "retrieval_query": None}
    item = resolved["item"]
    if item.get("craft") not in REVIEWED_ORNAMENT_CRAFTS:
        message = "这件对象的工艺资料当前无法安全确认，为避免误导，暂不作对象级讲解。"
        return {
            "message": message,
            "mode": "ornament_detail_unavailable",
            "evidence": [],
            "point_context": context,
            "presentation": presentation,
            "retrieval_query": None,
            "ornament_detail": {
                "ornament_id": item.get("ornament_id"),
                "node_id": item.get("node_id"),
                "coverage_level": "insufficient",
                "source_ids": [],
            },
        }
    detail = build_reviewed_instance_detail(
        item,
        rag_search,
        detailed=detailed,
        listen_only=listen_only,
        story_detail=story_detail,
    )
    message = detail["visitor_message"]
    evidence = detail["evidence"]
    detail_audit = detail["instance_detail"]
    if presentation:
        message += "\n\n本次对象说明未改变路线进度，您可继续使用现有导览操作。"
        presentation = {**presentation, "message": message, "code": "ornament_detail", "ok": True, "evidence_count": len(evidence)}
    return {
        "message": message,
        "mode": "ornament_detail",
        "evidence": evidence,
        "point_context": context,
        "presentation": presentation,
        "retrieval_query": detail["retrieval_query"],
        "ornament_detail": detail_audit,
    }


def build_reviewed_instance_detail(
    instance: dict[str, Any],
    rag_search: Callable[[str], str],
    *,
    detailed: bool = False,
    listen_only: bool = False,
    story_detail: bool = False,
) -> dict[str, Any]:
    """Retrieve and compactly render one already-resolved reviewed instance.

    The caller must supply a P1-10-selected object. This shared helper is the
    only bridge from a reviewed term association to object-level evidence: it
    queries with stable ID plus name, accepts only the same object's ``08``
    evidence, and never lets craft-overview or another object's packet supply
    a theme, scene, story, or meaning.
    """
    ornament_id = str(instance.get("ornament_id") or "").strip()
    name = str(instance.get("ornament_name") or instance.get("name") or "").strip()
    craft = str(instance.get("craft") or "").strip()
    node_id = str(instance.get("node_id") or "").strip()
    raw_location = instance.get("raw_location")
    if not all((ornament_id, name, craft, node_id)):
        raise ValueError("reviewed instance identity is incomplete")
    query = f"{ornament_id} {name} 陈家祠 建筑装饰 题材 画面 人物 故事 寓意"
    try:
        payload = parse_rag_payload(rag_search(query))
    except Exception:
        payload = {"evidence": []}
    retrieved = [entry for entry in payload.get("evidence", []) if isinstance(entry, dict)]
    accepted = filter_object_evidence(
        ornament_id=ornament_id,
        name=name,
        craft=craft,
        node_id=node_id,
        evidence=retrieved,
        strict_identity=True,
    )
    view = build_object_evidence_view(
        ornament_id=ornament_id,
        name=name,
        craft=craft,
        node_id=node_id,
        raw_location=raw_location if isinstance(raw_location, str) else None,
        evidence=accepted,
        strict_identity=True,
    )
    rendered = render_object_detail(
        view,
        first=True,
        detailed=detailed,
        listen_only=listen_only,
        compact=not detailed,
        story_detail=story_detail,
    )
    source_ids = list(rendered.source_ids)
    return {
        "retrieval_query": query,
        "visitor_message": rendered.visitor_text,
        "evidence": [dict(entry) for entry in accepted],
        "instance_detail": {
            "ornament_id": view.ornament_id,
            "node_id": view.node_id,
            "coverage_level": view.coverage_level,
            "source_ids": source_ids,
            "used_for_visitor_answer": bool(source_ids),
            "accepted_evidence": [dict(entry) for entry in accepted],
            "rejected_evidence": [
                {
                    "document": entry.get("document"),
                    "title_path": list(entry.get("title_path") or []),
                    "source_ids": list(entry.get("source_ids") or []),
                    "reason": "not_exact_ornament_evidence",
                }
                for entry in retrieved
                if entry not in accepted
            ],
        },
    }


def build_tour_qa_query(user_query: str, tour_state: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None]:
    """Augment one factual question with the active position's reviewed hints."""
    context, _ = resolve_point_context(user_query, tour_state)
    if not context:
        return user_query, None
    card = context.get("card") or {}
    detail_craft = next((craft for craft in CRAFT_TERMS if craft in user_query), None)
    candidate_items = card.get("ornaments", [])
    if detail_craft:
        candidate_items = [item for item in candidate_items if detail_craft in item.get("craft", "")]
    candidates = "、".join(item["name"] for item in candidate_items[:6] if item.get("name"))
    hints = [f"当前导览点位提示：{context['name']}（{context['node_id']}）"]
    if context.get("guide_focus"):
        hints.append(f"讲解关注方向：{context['guide_focus']}")
    if candidates:
        hints.append(f"可用于检索的已审核名称提示：{candidates}")
    glossary_hint = format_point_glossary_hint(context["node_id"], user_query)
    if glossary_hint:
        hints.append(glossary_hint)
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
    *,
    fact_kind: str | None = None,
) -> dict[str, Any]:
    """Format RAG evidence plus an unchanged A1 guide context as one response."""
    evidence = payload.get("evidence") or []
    context = current_stop_context(tour_state)
    fact_answer = render_single_fact_answer(
        user_query,
        evidence,
        fact_kind=fact_kind,
    )
    if fact_answer is not None:
        answer = fact_answer.message
        mode = "single_fact"
    elif evidence:
        answer = "根据本地知识库检索到的资料：\n" + "\n".join(
            _evidence_line(item) for item in evidence[:3] if isinstance(item, dict)
        )
        mode = "rag"
    else:
        detail = payload.get("error") or "当前本地知识库没有检索到足以支持该问题的资料。"
        answer = f"资料不足：{detail} 我不会根据当前点位补造事实。"
        mode = "rag"

    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if presentation:
        if fact_answer is None:
            point_name = context["name"] if context else "当前导览位置"
            answer += (
                f"\n\n您当前位于{point_name}。"
                "本次问答未改变路线进度，可继续使用现有导览操作。"
            )
        presentation = {
            **presentation,
            "message": answer,
            "code": (
                "tour_qa_single_fact_answer"
                if fact_answer is not None
                else ("tour_qa_answer" if evidence else "tour_qa_no_evidence")
            ),
            "ok": fact_answer.ok if fact_answer is not None else True,
            "evidence_count": len(evidence),
        }
    return {
        "message": answer,
        "evidence": evidence,
        "point_context": context,
        "presentation": presentation,
        "mode": mode,
        "single_fact": fact_answer.to_dict() if fact_answer is not None else None,
    }


def _current_point_craft_feature_request(user_query: str) -> str | None:
    """Return the named craft only for deictic current-point feature questions."""
    if not any(term in user_query for term in DEICTIC_POINT_TERMS):
        return None
    if not any(term in user_query for term in FEATURE_TERMS):
        return None
    return next((craft for craft in CRAFT_TERMS if craft in user_query), None)


def _current_point_craft_term_request(user_query: str) -> str | None:
    """Recognize a deictic craft definition only when it names the craft."""
    if not any(term in user_query for term in DEICTIC_POINT_TERMS):
        return None
    if not any(term in user_query for term in TERM_EXPLANATION_TERMS):
        return None
    return next((craft for craft in CRAFT_TERMS if craft in user_query), None)


def _current_point_craft_term_answer(
    user_query: str,
    craft: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
) -> dict[str, Any]:
    """Verify a local craft association before offering a term definition."""
    context = current_stop_context(tour_state)
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if not context or not context.get("card"):
        message = "当前没有可核对的已审核导览位置；请先到达一个点位，或直接说明要问的点位名称。"
        return {
            "message": message,
            "mode": "current_craft_unavailable",
            "evidence": [],
            "point_context": context,
            "presentation": {**presentation, "message": message, "code": "current_craft_unavailable", "ok": False} if presentation else None,
            "retrieval_query": None,
        }
    local_items = [
        item for item in context["card"].get("ornaments", [])
        if craft in str(item.get("craft") or "") and item.get("name")
    ]
    if not local_items:
        return answer_current_point_craft_features(
            user_query, craft, tour_state or {}, interaction_state, rag_search,
            point_context=context,
        )
    term_answer = answer_term_question(user_query, tour_state, interaction_state)
    if term_answer is None:
        # There is no permitted structured term card, so use the existing RAG
        # path while retaining the already-verified point boundary.
        return answer_current_point_craft_features(
            user_query, craft, tour_state or {}, interaction_state, rag_search,
            point_context=context,
        )
    message = (
        f"您当前位于{context['name']}。该点已审核关联清单中确有{craft}对象；\n"
        + term_answer["message"]
    )
    term_presentation = term_answer.get("presentation")
    if term_presentation:
        term_presentation = {**term_presentation, "message": message, "code": "current_point_term_card", "ok": True}
    return {
        **term_answer,
        "message": message,
        "mode": "current_point_term_card",
        "point_context": context,
        "presentation": term_presentation,
        "retrieval_query": None,
    }


def _comparison_rag_fallback(
    user_query: str,
    comparison: dict[str, Any],
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
) -> dict[str, Any]:
    """Retrieve each explicitly named comparison side without using a card."""
    subjects = extract_comparison_subjects(user_query)
    queries = [f"{subject} 是什么 工艺 特点" for subject in subjects[:2]]
    if len(queries) < 2:
        queries = [user_query]
    payloads: list[tuple[str, dict[str, Any]]] = []
    for subject, query in zip(subjects[:2] or ("该比较问题",), queries):
        try:
            payloads.append((subject, parse_rag_payload(rag_search(query))))
        except Exception as exc:
            payloads.append((subject, {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}))
    evidence = [
        item
        for _, payload in payloads
        for item in payload.get("evidence", [])
        if isinstance(item, dict)
    ]
    prefix = format_gated_comparison_answer(comparison)
    lines = [prefix, "以下仅依据基础资料分别检索，不是研究比较卡结论："]
    for subject, payload in payloads:
        subject_evidence = [item for item in payload.get("evidence", []) if isinstance(item, dict)]
        if subject_evidence:
            lines.append(f"- {subject}：{_evidence_line(subject_evidence[0])}")
        else:
            lines.append(f"- {subject}：资料不足，暂不据此补写差异。")
    lines.append("只有两方都有足够证据时才适合继续归纳异同；当前不会用常识补齐缺失一方。")
    message = "\n".join(lines)
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if presentation:
        message += "\n\n本次比较未改变路线进度，您可继续使用现有导览操作。"
        presentation = {**presentation, "message": message, "code": "comparison_rag_fallback", "ok": True, "evidence_count": len(evidence)}
    return {
        "message": message,
        "mode": "comparison_rag_fallback",
        "comparison": None,
        "evidence": evidence,
        "point_context": current_stop_context(tour_state),
        "presentation": presentation,
        "retrieval_query": queries,
        "comparison_subjects": subjects[:2],
    }


def _matches_ornament_evidence(item: dict[str, Any], ornament_name: str) -> bool:
    """Do not present a global RAG result as an on-site instance by accident."""
    title = " ".join(item.get("title_path") or [])
    content = str(item.get("content") or "")
    return ornament_name in title or ornament_name in content


def _fact_summary(item: dict[str, Any]) -> str:
    """Use a compact evidence-derived sentence rather than dumping a chunk."""
    content = " ".join(str(item.get("content") or "").split())
    first_sentence = next((part.strip() for part in content.replace("！", "。").replace("？", "。").split("。") if part.strip()), content)
    source_ids = "、".join(item.get("source_ids") or []) or "未标注来源编号"
    document = item.get("document") or "未标注文档"
    return f"{first_sentence}（{document}；{source_ids}）"


def answer_current_point_craft_features(
    user_query: str,
    craft: str,
    tour_state: dict[str, Any],
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    point_context: dict[str, Any] | None = None,
    detailed: bool = False,
) -> dict[str, Any]:
    """Give a point-bounded craft explanation plus evidence-backed craft facts.

    The point card proves only the reviewed ornament-to-node association.  The
    RAG calls prove explanatory facts.  This distinction prevents global
    examples from being described as objects immediately in front of a visitor.
    """
    context = point_context or current_stop_context(tour_state)
    is_physical_context = bool(
        context and context.get("node_id") == tour_state.get("current_stop_id")
    )
    presentation = present_tour_state(tour_state, interaction_state) if interaction_state else None
    if not context or not context.get("card"):
        message = "当前没有可用的已审核点位讲解包，无法把“这里”安全限定为具体现场实例。"
        return {"message": message, "evidence": [], "point_context": context, "presentation": presentation, "mode": "current_craft_unavailable", "retrieval_query": None}

    local_items = [
        item for item in context["card"].get("ornaments", [])
        if craft in str(item.get("craft") or "") and item.get("name")
    ]
    if not local_items:
        message = (
            f"您当前位于{context['name']}。该点的已审核关联清单中没有{craft}，"
            "因此我不会把全馆其他位置的同类装饰当作您眼前的实例。"
        )
        if presentation:
            presentation = {**presentation, "message": message, "code": "current_craft_absent", "ok": True, "evidence_count": 0}
        return {"message": message, "evidence": [], "point_context": context, "presentation": presentation, "mode": "current_craft_absent", "retrieval_query": None}

    rag_queries = [f"{craft} 是什么 有什么特点"]
    rag_queries.extend(f"{item['name']} {craft} 特点" for item in local_items)
    payloads: list[dict[str, Any]] = []
    for query in rag_queries:
        try:
            payloads.append(parse_rag_payload(rag_search(query)))
        except Exception as exc:
            payloads.append({"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"})

    craft_evidence = [item for item in payloads[0].get("evidence", []) if isinstance(item, dict)]
    retrieval_errors = [str(payload.get("error")) for payload in payloads if payload.get("error")]
    instance_evidence: dict[str, list[dict[str, Any]]] = {}
    for local, payload in zip(local_items, payloads[1:]):
        instance_evidence[local["name"]] = [
            item for item in payload.get("evidence", [])
            if isinstance(item, dict) and _matches_ornament_evidence(item, local["name"])
        ]
    evidence = [*craft_evidence]
    evidence.extend(item for values in instance_evidence.values() for item in values)

    sections = [f"您现在位于{context['name']}。这里的{craft}可以从“工艺特点”和“眼前实例”两层看："]
    if not is_physical_context:
        sections[0] = f"您问的是{context['name']}的{craft}，可以从“工艺特点”和“该点审核实例”两层看："
    if detailed:
        sections.append("- 展开说明：以下实例只限于该点已审核关联对象；每项解释均重新检索后再引用。")
    if craft_evidence:
        sections.append(f"- 工艺特点：{_fact_summary(craft_evidence[0])}")
    else:
        availability = "本地知识检索暂时不可用；" if retrieval_errors else ""
        sections.append(f"- 工艺特点：{availability}资料不足；本地知识库暂未检索到足以概括{craft}特点的可引用资料。")
    sections.append("- 本点已审核关联的实例：" + "、".join(item["name"] for item in local_items) + "。")
    sourced_instances = []
    for local in local_items:
        matches = instance_evidence[local["name"]]
        if matches:
            sourced_instances.append(f"  - {local['name']}：{_fact_summary(matches[0])}")
    if sourced_instances:
        sections.extend(sourced_instances)
    else:
        sections.append("- 上述实例的现场关联已经审核；但当前检索未找到可逐件引用的解释，因此不据名称补造寓意或故事。")
    sections.append("您可以继续查看本点讲解、结束讲解，或在下方选择其他导览操作；本次问答未改变路线进度。")
    message = "\n".join(sections)
    if presentation:
        presentation = {**presentation, "message": message, "code": "current_point_craft_features", "ok": True, "evidence_count": len(evidence)}
    return {
        "message": message,
        "evidence": evidence,
        "point_context": context,
        "presentation": presentation,
        "mode": "current_point_craft_features",
        "retrieval_query": rag_queries,
        "local_ornaments": [{"ornament_id": item.get("ornament_id"), "name": item["name"], "craft": item.get("craft")} for item in local_items],
    }


def _feature_craft(user_query: str) -> str | None:
    if not any(term in user_query for term in FEATURE_TERMS):
        return None
    return next((craft for craft in CRAFT_TERMS if craft in user_query), None)


def build_qa_context_from_answer(
    user_query: str,
    result: dict[str, Any],
    tour_state: dict[str, Any] | None,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Create one follow-up context only for a successful bounded QA result.

    A reviewed whole-site craft definition is also bounded: it carries one
    explicit craft name from the terminology registry, but deliberately no
    physical node.  This lets ``灰塑是什么 → 详细讲讲`` keep its topic while
    preventing an unrelated or deictic location from being inferred.
    """
    mode = result.get("mode")
    context = result.get("point_context")
    evidence = result.get("evidence") or []
    term = result.get("term") if isinstance(result.get("term"), dict) else {}
    term_craft = next((craft for craft in CRAFT_TERMS if term.get("zh") == craft), None)
    is_definition = any(token in user_query for token in TERM_EXPLANATION_TERMS)
    is_whole_site_term = mode == "term_card" and term_craft is not None and is_definition
    is_whole_site_craft_follow_up = mode in {
        "whole_site_craft_overview",
        "qa_follow_up_global_craft",
    }
    if mode not in {"inventory", "current_point_craft_features", "rag"} and not is_whole_site_term and not is_whole_site_craft_follow_up:
        return None
    # A craft explanation without retrieved evidence is a safe fallback, but
    # it is not a trustworthy basis for a later omitted follow-up.  Inventory
    # is intentionally different: it is a successful deterministic reviewed
    # association list rather than an attempted RAG explanation.
    if mode in {
        "rag",
        "current_point_craft_features",
        "whole_site_craft_overview",
        "qa_follow_up_global_craft",
    } and not evidence:
        return None

    try:
        previous = validate_qa_context(previous_context) if previous_context else None
    except ValueError:
        previous = None

    if is_whole_site_term or is_whole_site_craft_follow_up:
        craft = term_craft or next(
            (value for value in (previous or {}).get("subject_terms", ()) if value in CRAFT_TERMS),
            None,
        )
        if not craft:
            return None
        return create_qa_context(
            query_node_id=None,
            origin="whole_site",
            subject_kind="craft",
            subject_terms=[craft],
            answer_mode=mode,
            follow_up_allowed=True,
            physical_node_id_snapshot=(tour_state or {}).get("current_stop_id"),
            suggested_follow_up_ornament_ids=result.get("suggested_follow_up_ornament_ids", ()),
        )

    if not isinstance(context, dict) or not context.get("node_id"):
        return None
    resolution = resolve_reviewed_node(user_query)
    origin = (
        previous["origin"]
        if previous and context["node_id"] == previous.get("query_node_id") and not resolution.node_id
        else ("explicit_node" if resolution.node_id else "physical_deictic")
    )
    # A detail request normally does not repeat the object name.  Keep the
    # previous structured subject only when this answer stayed in the same
    # bounded point context; never infer it from old RAG text.
    previous_craft = None
    if previous and context["node_id"] == previous.get("query_node_id") and not resolution.node_id:
        previous_craft = next(
            (term for term in previous.get("subject_terms", ()) if term in CRAFT_TERMS),
            None,
        )
    result_craft = next(
        (
            item.get("craft")
            for item in result.get("local_ornaments", [])
            if item.get("craft") in CRAFT_TERMS
        ),
        None,
    )
    craft = next((term for term in CRAFT_TERMS if term in user_query), None) or result_craft or previous_craft
    subject_kind = "craft" if craft else ("inventory" if mode == "inventory" else "fact")
    return create_qa_context(
        query_node_id=context["node_id"],
        origin=origin,
        subject_kind=subject_kind,
        subject_terms=[craft] if craft else [],
        answer_mode=mode,
        follow_up_allowed=bool(craft or mode == "inventory"),
        physical_node_id_snapshot=(tour_state or {}).get("current_stop_id"),
    )


def _answer_whole_site_craft_follow_up(
    craft: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    detailed: bool = True,
    mode: str = "qa_follow_up_global_craft",
    instance_node_id: str | None = None,
    instance_context_origin: str = "whole_site",
) -> dict[str, Any]:
    """Render one canonical reviewed craft section without vector ranking."""
    try:
        record = load_craft_record(craft)
        evidence = [record.as_evidence()]
        message = render_craft_explanation(
            record, "detailed" if detailed else "brief"
        )
        enhancement = runtime_term_instance_enhancement(
            craft, current_node_id=instance_node_id
        )
        instance_details: list[dict[str, Any]] = []
        if enhancement and enhancement["term_instances"]:
            examples = "；".join(
                f"{item['point_name']}的“{item['ornament_name']}”（{item['craft']}）"
                for item in enhancement["term_instances"]
            )
            if enhancement["instance_scope"] == "whole_site":
                label = "陈家祠全馆审核关联实例"
            elif instance_context_origin == "explicit_query_location":
                label = "所问点位的审核关联实例"
            else:
                label = "当前点的审核关联实例"
            message += f"\n\n作为{label}，可参考：{examples}。现场可见情况请以实际为准。"
            # Whole-site references remain short names only. A reliable point
            # may add one compact, same-object ``08`` detail per selected
            # audited instance; each packet is retrieved and gated alone.
            if enhancement["instance_scope"] == "current_node":
                for instance in enhancement["term_instances"]:
                    try:
                        detail = build_reviewed_instance_detail(
                            instance,
                            rag_search,
                            detailed=False,
                        )
                    except (TypeError, ValueError):
                        # Association metadata can safely name a reviewed
                        # instance even when a malformed packet prevents its
                        # optional object-detail expansion.  Never let that
                        # failure borrow another object's evidence.
                        message += (
                            f"\n\n现有资料不足以安全展开“{instance['ornament_name']}”"
                            "的具体题材或故事。"
                        )
                        continue
                    instance_details.append(detail["instance_detail"])
                    message += f"\n\n{detail['visitor_message']}"
                    evidence.extend(detail["evidence"])
        elif enhancement and enhancement["instance_scope"] == "current_node":
            subject = "所问点位" if instance_context_origin == "explicit_query_location" else "当前点"
            message += f"\n\n{subject}的已审核关联清单中暂未找到该工艺实例。"
            instance_details = []
        else:
            instance_details = []
        error = None
    except CraftKnowledgeError as exc:
        evidence = []
        error = str(exc)
        message = f"暂时不能安全展开“{craft}”：{error}"
        enhancement = None
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if presentation:
        message += "\n\n本次术语展开未改变路线进度，您可继续使用现有导览操作。"
        presentation = {
            **presentation,
            "message": message,
            "code": mode if evidence else f"{mode}_no_evidence",
            "ok": bool(evidence),
            "evidence_count": len(evidence),
        }
    return {
        "message": message,
        "mode": mode,
        "evidence": evidence,
        "point_context": None,
        "presentation": presentation,
        "retrieval_query": None,
        "retrieval_strategy": "canonical_craft_section",
        "term": (
            dict(enhancement["term"])
            if enhancement is not None
            else {
                "zh": craft,
                "source_ids": list(evidence[0]["source_ids"]) if evidence else [],
            }
        ),
        "term_instances": (
            list(enhancement["term_instances"]) if enhancement else []
        ),
        "instance_details": instance_details,
        "suggested_follow_up_ornament_ids": [
            detail["ornament_id"]
            for detail in instance_details
            if detail.get("used_for_visitor_answer")
        ],
        "instance_context_origin": instance_context_origin,
        "error": error,
    }


def answer_qa_follow_up_detail(
    user_query: str,
    qa_context: dict[str, Any] | None,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    detailed: bool = True,
) -> dict[str, Any]:
    """Re-retrieve a single bounded QA follow-up without changing tour progress."""
    requested_craft = next((craft for craft in CRAFT_TERMS if craft in user_query), None)
    try:
        context = validate_qa_context(qa_context)
    except ValueError:
        context = None
    if not context or not context["follow_up_allowed"]:
        # An explicit reviewed craft in the current turn is sufficient.  It is
        # not an omitted-subject follow-up, so it must not be blocked merely
        # because no prior point or route context exists.
        if requested_craft:
            return _answer_whole_site_craft_follow_up(
                requested_craft, tour_state, interaction_state, rag_search
            )
        return {
            "message": "我没有可安全继续展开的上一轮点位问答。请说明想了解哪个点位或哪类装饰。",
            "mode": "qa_follow_up_clarification",
            "evidence": [],
            "point_context": None,
            "presentation": present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None,
            "retrieval_query": None,
        }

    craft = requested_craft or next(
        (term for term in context["subject_terms"] if term in CRAFT_TERMS), None
    )
    if context["origin"] == "whole_site" and context["query_node_id"] is None:
        if not craft:
            return {
                "message": "上一轮术语说明没有唯一可展开的工艺名称，请说明想继续了解哪一种装饰。",
                "mode": "qa_follow_up_clarification",
                "evidence": [],
                "point_context": None,
                "presentation": present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None,
                "retrieval_query": None,
            }
        return _answer_whole_site_craft_follow_up(craft, tour_state, interaction_state, rag_search)

    if not context["query_node_id"]:
        return {
            "message": "我没有可安全继续展开的上一轮点位问答。请说明想了解哪个点位或哪类装饰。",
            "mode": "qa_follow_up_clarification",
            "evidence": [],
            "point_context": None,
            "presentation": present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None,
            "retrieval_query": None,
        }

    point_context = point_context_for_node(context["query_node_id"])
    if not craft:
        return {
            "message": f"上一轮问答限定在{point_context['name']}，但没有唯一可展开的对象。请说明想继续了解哪一种装饰。",
            "mode": "qa_follow_up_clarification",
            "evidence": [],
            "point_context": point_context,
            "presentation": present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None,
            "retrieval_query": None,
        }
    if not point_context.get("card"):
        return {
            "message": f"{point_context['name']}缺少已审核讲解包，无法安全展开上一轮问答。",
            "mode": "qa_follow_up_clarification",
            "evidence": [],
            "point_context": point_context,
            "presentation": present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None,
            "retrieval_query": None,
        }
    return answer_current_point_craft_features(
        user_query,
        craft,
        tour_state or {},
        interaction_state,
        rag_search,
        point_context=point_context,
        detailed=detailed,
    )


def answer_tour_question(
    user_query: str,
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    visitor_profile: dict[str, Any] | None = None,
    *,
    normalized_fact_kind: str | None = None,
    normalized_knowledge_plan: ControlledKnowledgePlan | None = None,
    pending_ornament_clarification: dict[str, Any] | None = None,
    grounded_knowledge_renderer: (
        Callable[[ControlledKnowledgePlan, list[dict[str, Any]]], str] | None
    ) = None,
) -> dict[str, Any]:
    """Use one injected existing RAG callable and leave both state snapshots untouched."""
    safety_answer = answer_visit_safety_question(user_query)
    if safety_answer is not None:
        presentation = (
            present_tour_state(tour_state, interaction_state)
            if tour_state and interaction_state
            else None
        )
        if presentation:
            presentation = {
                **presentation,
                "message": safety_answer["message"],
                "code": "tour_qa_visit_safety_answer",
                "ok": safety_answer["verified"],
            }
        return {
            "message": safety_answer["message"],
            "mode": "visit_safety",
            "evidence": [],
            "point_context": current_stop_context(tour_state),
            "presentation": presentation,
            "retrieval_query": None,
        }
    if not (
        is_explicit_photo_request(user_query)
        or is_explicit_research_question(user_query)
        or is_explicit_comparison_question(user_query)
    ):
        pending_answer = _answer_pending_ornament_choice(
            user_query,
            pending_ornament_clarification,
            tour_state,
            interaction_state,
            rag_search,
            visitor_profile,
        )
        if pending_answer is not None:
            return pending_answer
    craft_location_request = parse_craft_location_request(user_query)
    if craft_location_request is not None:
        answer = render_craft_location_answer(craft_location_request)
        presentation = (
            present_tour_state(tour_state, interaction_state)
            if tour_state and interaction_state
            else None
        )
        message = answer.message
        if presentation:
            message += "\n\n本次位置说明未改变路线进度，您可继续使用现有导览操作。"
            presentation = {
                **presentation,
                "message": message,
                "code": "multi_craft_location_answer",
                "ok": not answer.missing_crafts,
                "evidence_count": len(answer.evidence),
            }
        return {
            "message": message,
            "mode": "multi_craft_location",
            "evidence": list(answer.evidence),
            "point_context": current_stop_context(tour_state),
            "presentation": presentation,
            "retrieval_query": None,
            "retrieval_strategy": "canonical_craft_location_fields",
            "requested_crafts": list(craft_location_request.crafts),
            "missing_crafts": list(answer.missing_crafts),
        }
    fact_kind = normalized_fact_kind or identify_single_fact_kind(user_query)
    fact_categories = (
        single_fact_categories_for_kind(fact_kind)
        if fact_kind is not None
        else None
    )
    if fact_categories is not None:
        try:
            payload = parse_rag_payload(rag_search(user_query))
        except Exception as exc:
            payload = {
                "evidence": [],
                "error": f"本地知识检索暂时不可用：{exc}",
            }
        result = format_tour_qa_answer(
            user_query,
            payload,
            tour_state,
            interaction_state,
            fact_kind=fact_kind,
        )
        return {
            **result,
            "retrieval_query": user_query,
            "point_context": current_stop_context(tour_state),
        }
    # P1-05 owns the seven generic craft explanations.  Their canonical
    # section remains the factual body; D1 only contributes gated reviewed
    # instances after it.  An explicit point or the physical current point
    # affects instance ranking, never TourState itself.
    is_research_question = is_explicit_research_question(user_query)
    is_comparison_question = is_explicit_comparison_question(user_query)
    craft_request = (
        None
        if is_research_question or is_comparison_question or is_explicit_photo_request(user_query)
        else parse_craft_explanation_request(user_query)
    )
    scoped_context, _ = resolve_point_context(user_query, tour_state)
    if (
        craft_request is None
        and not is_research_question
        and not is_comparison_question
        and not is_explicit_photo_request(user_query)
        and scoped_context is not None
    ):
        named_crafts = [craft for craft in CRAFT_TERMS if craft in user_query]
        if (
            len(named_crafts) == 1
            and any(token in user_query for token in TERM_EXPLANATION_TERMS)
        ):
            craft_request = CraftExplanationRequest(named_crafts[0], "brief")
    physical_context = current_stop_context(tour_state)
    instance_context = scoped_context or physical_context
    explicit_node_resolution = resolve_reviewed_node(user_query)
    # A named audited object is narrower than a semantic ``ornament_item``
    # proposal.  Respect an explicit craft-only proof restriction instead of
    # silently retrieving a different, object-level source packet.
    story_scope = (
        None
        if is_research_question or is_comparison_question or is_explicit_photo_request(user_query)
        else resolve_ornament_story_scope_request(user_query, tour_state)
    )
    if story_scope is not None:
        if story_scope["resolved"].get("status") == "ambiguous":
            candidates = _candidate_categories_for_ambiguous_ornaments(
                story_scope["resolved"],
            )
            # An explicit craft can narrow a *candidate category*, but never
            # turns an internally indistinguishable group into one object.  A
            # craft-only request still receives the P1-20 source-scope refusal
            # without querying any object packet.
            craft_categories = [
                candidate for candidate in candidates
                if candidate["craft"] in user_query
            ]
            if story_scope.get("requested_scope") == "craft_only" and len(craft_categories) == 1:
                category = craft_categories[0]
                source_scope = _ornament_story_source_clarification(
                    {
                        "resolved": story_scope["resolved"],
                        "requested_subject": f"{category['craft']}《{category['display_name']}》",
                        "requested_scope": "craft_only",
                    },
                    tour_state,
                    interaction_state,
                )
                return {
                    **source_scope,
                    "ornament_candidate_audit": {
                        "candidate_kind": category["candidate_kind"],
                        "craft": category["craft"],
                        "ornament_id": category.get("ornament_id"),
                        "member_ornament_ids": list(category.get("member_ornament_ids") or []),
                        "selectable_for_exact_detail": category["selectable_for_exact_detail"],
                        "blocked_reason": category.get("blocked_reason"),
                    },
                }
            if len(candidates) >= 2:
                pending = create_pending_ornament_clarification(
                    original_query=user_query,
                    subject_name=candidates[0]["display_name"],
                    candidates=candidates,
                    requested_detail="story",
                    evidence_scope=story_scope.get("requested_scope", "exact_ornament"),
                )
                return {
                    "message": _render_ornament_candidate_clarification(
                        pending["subject_name"], candidates,
                    ),
                    "mode": "ornament_candidate_clarification",
                    "answer_mode": "ornament_candidate_clarification",
                    "evidence": [],
                    "source_ids": [],
                    "point_context": story_scope["resolved"].get("context"),
                    "presentation": None,
                    "retrieval_query": None,
                    "pending_ornament_clarification": pending,
                    "ornament_candidates": candidates,
                }
        if story_scope.get("requested_scope") == "craft_only":
            return _ornament_story_source_clarification(
                story_scope, tour_state, interaction_state,
            )
        return _answer_ornament_detail(
            story_scope["resolved"],
            tour_state,
            interaction_state,
            rag_search,
            detailed=True,
            story_detail=True,
            listen_only=(visitor_profile or {}).get("interaction_mode") == "listen_only",
        )
    if craft_request is not None:
        return _answer_whole_site_craft_follow_up(
            craft_request.craft,
            tour_state,
            interaction_state,
            rag_search,
            detailed=craft_request.detail_level == "detailed",
            mode=(
                "qa_follow_up_global_craft"
                if craft_request.detail_level == "detailed"
                else "whole_site_craft_overview"
            ),
            instance_node_id=(instance_context or {}).get("node_id"),
            instance_context_origin=(
                "explicit_query_location"
                if explicit_node_resolution.node_id is not None
                else ("physical_location" if physical_context is not None else "whole_site")
            ),
        )
    # A caller may carry a broad semantic plan from normalization. It cannot
    # override another exact, runtime-eligible term request. Research and
    # comparison retain their own higher-priority handlers.
    current_term_craft = _current_point_craft_term_request(user_query)
    if current_term_craft:
        return _current_point_craft_term_answer(
            user_query, current_term_craft, tour_state, interaction_state, rag_search,
        )
    if (
        is_explicit_term_question(user_query)
        and not is_research_question
        and not is_comparison_question
        and not is_explicit_photo_request(user_query)
        and _resolve_ornament_detail_request(user_query, tour_state) is None
    ):
        term_answer = answer_term_question(user_query, tour_state, interaction_state)
        if term_answer is not None:
            return {
                **term_answer,
                "retrieval_query": None,
                "point_context": current_stop_context(tour_state),
            }
    if normalized_knowledge_plan is not None:
        try:
            payload = parse_rag_payload(rag_search(user_query))
        except Exception as exc:
            payload = {
                "evidence": [],
                "error": f"本地知识检索暂时不可用：{exc}",
            }
        evidence = payload.get("evidence") or []
        if grounded_knowledge_renderer is None:
            message = (
                "当前受控知识回答器不可用，我不会直接展示检索原文或使用无关资料补答。"
            )
        else:
            message = grounded_knowledge_renderer(
                normalized_knowledge_plan,
                evidence,
            )
        presentation = (
            present_tour_state(tour_state, interaction_state)
            if tour_state and interaction_state
            else None
        )
        if presentation:
            presentation = {
                **presentation,
                "message": message,
                "code": "tour_qa_controlled_knowledge_answer",
                "ok": bool(evidence),
                "evidence_count": len(evidence),
            }
        return {
            "message": message,
            "mode": "controlled_knowledge",
            "evidence": evidence,
            "knowledge_plan": normalized_knowledge_plan.to_dict(),
            "point_context": current_stop_context(tour_state),
            "presentation": presentation,
            "retrieval_query": user_query,
        }
    if is_explicit_photo_request(user_query):
        context, error_code = resolve_point_context(user_query, tour_state)
        if error_code in {"ambiguous_node_name", "multiple_node_mentions", "unknown_point"}:
            message = "我无法确定您提到的拍摄点位，请使用地图中的明确点位名称，或直接询问全馆的项目编辑拍摄候选。"
            presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
            if presentation:
                presentation = {**presentation, "message": message, "code": "photo_point_clarification", "ok": False}
            return {"message": message, "mode": "photo_point_clarification", "evidence": [], "point_context": None, "presentation": presentation, "retrieval_query": None}
        # A whole-site request can still prioritize the real current position,
        # but this is only a ranking hint and never a state update.
        context = context or current_stop_context(tour_state)
        result = answer_photo_request(
            user_query,
            point_context=context,
            tour_state=tour_state,
            visitor_profile=visitor_profile,
        )
        presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
        if presentation:
            message = result["message"] + "\n\n本次拍摄建议未改变路线或游览进度。"
            presentation = {**presentation, "message": message, "code": result["mode"], "ok": result["mode"] == "photo_recommendation"}
            result = {**result, "message": message, "presentation": presentation}
        else:
            result = {**result, "presentation": None}
        return {**result, "evidence": [], "retrieval_query": None}
    # A uniquely named reviewed object at a reviewed point is narrower than a
    # point inventory.  Resolve it before broad “讲讲月台” wording can return
    # every object at that point.
    ornament_request = _resolve_ornament_detail_request(user_query, tour_state)
    if ornament_request is not None:
        return _answer_ornament_detail(
            ornament_request,
            tour_state,
            interaction_state,
            rag_search,
            detailed=any(token in user_query for token in ("详细", "再讲")),
            listen_only=(visitor_profile or {}).get("interaction_mode") == "listen_only",
        )
    # A named craft plus a feature question is an evidence-backed explanatory
    # request, not a bare point inventory.  Check it before the broad
    # "有什么" inventory wording so "月台上的石雕有什么特点" cannot lose its
    # explicit-node scope to the list renderer.
    resolved_context, _ = resolve_point_context(user_query, tour_state)
    explicit_craft = _feature_craft(user_query)
    if explicit_craft and resolved_context:
        return answer_current_point_craft_features(
            user_query,
            explicit_craft,
            tour_state or {},
            interaction_state,
            rag_search,
            point_context=resolved_context,
        )
    current_term_craft = _current_point_craft_term_request(user_query)
    if current_term_craft:
        return _current_point_craft_term_answer(
            user_query, current_term_craft, tour_state, interaction_state, rag_search,
        )
    if is_point_inventory_request(user_query, tour_state):
        return {**format_point_inventory(user_query, tour_state, interaction_state), "retrieval_query": None, "evidence": []}
    current_craft = _current_point_craft_feature_request(user_query)
    if current_craft and tour_state:
        return answer_current_point_craft_features(
            user_query, current_craft, tour_state, interaction_state, rag_search
        )
    if is_explicit_comparison_question(user_query):
        explicit_research = any(token in user_query for token in ("研究", "学术", "论文", "文献"))
        profile = visitor_profile or {}
        allow_research = explicit_research or profile.get("audience_mode") == "study" or profile.get("knowledge_level") == "professional"
        comparison = retrieve_gated_comparison(user_query, allow_research=allow_research)
        if comparison.get("status") == "ambiguous_objects":
            message = format_gated_comparison_answer(comparison)
            presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
            if presentation:
                message += "\n\n本次澄清未改变路线进度，您可继续使用现有导览操作。"
                presentation = {**presentation, "message": message, "code": "comparison_clarification", "ok": False}
            return {"message": message, "mode": "comparison_clarification", "evidence": [], "point_context": None, "presentation": presentation, "retrieval_query": None}
        if comparison.get("status") == "ok":
            retrieval_query, context = build_tour_qa_query(user_query, tour_state)
            try:
                payload = parse_rag_payload(rag_search(retrieval_query))
            except Exception as exc:
                payload = {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}
            message = format_gated_comparison_answer(comparison)
            source_ids = [source for item in payload.get("evidence", []) for source in item.get("source_ids", [])]
            if source_ids:
                message += f"\n基础事实交叉核对（来源：{'、'.join(dict.fromkeys(source_ids))}）。"
            presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
            if presentation:
                message += "\n\n本次比较未改变路线进度，您可继续使用现有导览操作。"
                presentation = {**presentation, "message": message, "code": "comparison_card_answer", "ok": True}
            return {"message": message, "mode": "comparison_card", "evidence": payload.get("evidence", []), "comparison": comparison.get("card"), "point_context": context, "presentation": presentation, "retrieval_query": retrieval_query}
        return _comparison_rag_fallback(
            user_query, comparison, tour_state, interaction_state, rag_search,
        )
    if is_explicit_research_question(user_query):
        research = retrieve_research_cards(
            user_query, current_node_id=(tour_state or {}).get("current_stop_id")
        )
        retrieval_query, context = build_tour_qa_query(user_query, tour_state)
        try:
            payload = parse_rag_payload(rag_search(retrieval_query))
        except Exception as exc:
            payload = {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}
        if research.get("cards"):
            answer = format_research_answer(
                research,
                knowledge_level=(visitor_profile or {}).get("knowledge_level", "general"),
                base_evidence=payload.get("evidence", []),
            )
            mode = "research_card"
            presentation_code = "research_card_answer"
        else:
            # A research-shaped question may have no D1-eligible exact card.
            # In that case the existing factual RAG remains useful, but must
            # be visibly framed as a basic-source answer rather than research.
            fallback = format_tour_qa_answer(user_query, payload, tour_state, interaction_state)
            answer = (
                "暂未找到可安全引用、且与该问题直接匹配的研究摘要；"
                "以下仅依据基础资料回答，不是研究卡结论。\n\n"
                + fallback["message"]
            )
            mode = "research_rag_fallback"
            presentation_code = "research_rag_fallback"
        presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
        if presentation:
            answer += "\n\n本次研究说明未改变路线进度，您可继续使用现有导览操作。"
            presentation = {**presentation, "message": answer, "code": presentation_code, "ok": True}
        return {
            "message": answer, "mode": mode, "evidence": payload.get("evidence", []),
            "research_cards": research.get("cards", []), "point_context": context,
            "presentation": presentation, "retrieval_query": retrieval_query,
        }
    term_answer = answer_term_question(user_query, tour_state, interaction_state)
    if term_answer is not None:
        return {**term_answer, "retrieval_query": None, "point_context": current_stop_context(tour_state)}
    retrieval_query, context = build_tour_qa_query(user_query, tour_state)
    try:
        payload = parse_rag_payload(rag_search(retrieval_query))
    except Exception as exc:  # The adapter must never let retrieval break a tour.
        payload = {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}
    result = format_tour_qa_answer(user_query, payload, tour_state, interaction_state)
    return {**result, "retrieval_query": retrieval_query, "point_context": context}
