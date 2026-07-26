"""B3 evidence orchestration for one deterministic StopProgram.

This module reuses the existing RAG callable.  It does not create an index,
change a route, or write TourState; only the A1 interaction adapter may do
that.  Point-card data determines the approved objects to cover, while RAG
evidence is the sole source for cultural or craft facts in the output.
"""

from __future__ import annotations

from typing import Any, Callable

from guide_program_planner import StopProgram, plan_stop_program
from guide_narration import compose_guide_narration
from tour_presenter import present_tour_state
from tour_qa import load_guide_cards, parse_rag_payload


def content_budget_seconds_for_stop(node_id: str) -> int | None:
    """Read the reviewed route allocation for a stop, excluding walking time."""
    card = load_guide_cards().get(node_id)
    if not card:
        return None
    minutes = card.get("recommended_visit_minutes")
    return int(minutes) * 60 if isinstance(minutes, int) and minutes > 0 else None


def _is_active_planned_stop(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> bool:
    if not tour_state or not interaction_state:
        return False
    current = tour_state.get("current_stop_id")
    return bool(
        current
        and current == interaction_state.get("pending_stop_id")
        and current in tour_state.get("remaining_stop_ids", [])
        and interaction_state.get("stop_phase") in {"explaining", "awaiting_confirmation"}
    )


def _evidence_line(item: dict[str, Any]) -> str:
    document = item.get("document") or "未标注文档"
    title_path = item.get("title_path") or []
    title = " / ".join(title_path[-2:]) if isinstance(title_path, list) and title_path else document
    source_ids = "、".join(item.get("source_ids") or []) or "未标注来源编号"
    content = " ".join(str(item.get("content") or "").split())
    excerpt = content[:180] + ("…" if len(content) > 180 else "")
    return f"{document} / {title}（来源：{source_ids}）：{excerpt}"


def _program_from_state(
    tour_state: dict[str, Any],
    current_program: dict[str, Any] | None,
) -> StopProgram | None:
    """Use an existing current-stop program only when it is still applicable."""
    # The serialized program is retained by Agent state for audit and UI use,
    # but a fresh immutable StopProgram is cheap and avoids trusting UI input.
    node_id = tour_state.get("current_stop_id")
    budget = content_budget_seconds_for_stop(node_id)
    if not node_id or budget is None:
        return None
    return plan_stop_program(
        node_id,
        budget,
        interests=tour_state.get("interests", []),
        detail_level=tour_state.get("detail_level", "standard"),
    )


def build_stop_guidance(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    current_program: dict[str, Any] | None = None,
    detailed: bool = False,
) -> dict[str, Any]:
    """Return sourced guidance for the active stop without mutating tour state."""
    presentation = present_tour_state(tour_state, interaction_state) if tour_state and interaction_state else None
    if not _is_active_planned_stop(tour_state, interaction_state):
        message = "请先到达当前正式讲解点后再开始本点讲解。"
        return {
            "message": message,
            "status": "inactive_stop",
            "stop_program": None,
            "evidence": [],
            "rag_queries": [],
            "presentation": {**presentation, "message": message, "ok": False, "code": "guidance_inactive_stop"} if presentation else None,
        }

    assert tour_state is not None and interaction_state is not None
    program = _program_from_state(tour_state, current_program)
    if program is None:
        message = "当前点位缺少已审核的讲解内容预算或讲解包，无法安全生成本点讲解。"
        return {
            "message": message,
            "status": "program_unavailable",
            "stop_program": None,
            "evidence": [],
            "rag_queries": [],
            "presentation": {**present_tour_state(tour_state, interaction_state), "message": message, "ok": False, "code": "guidance_program_unavailable"},
        }

    if not program.selected_items:
        message = f"{program.display_name} 暂无已审核的可讲解文物候选，因此不生成推测性讲解。"
        return {
            "message": message,
            "status": "no_reviewed_candidates",
            "stop_program": program.to_dict(),
            "evidence": [],
            "rag_queries": [],
            "presentation": {**present_tour_state(tour_state, interaction_state), "message": message, "code": "guidance_no_candidates", "ok": True},
        }

    evidence: list[dict[str, Any]] = []
    rag_queries: list[str] = []
    evidence_by_item: dict[str, list[dict[str, Any]]] = {}
    for item in program.selected_items:
        query = item.rag_query_hints[0]
        rag_queries.append(query)
        try:
            payload = parse_rag_payload(rag_search(query))
        except Exception as exc:
            payload = {"evidence": [], "error": f"本地知识检索暂时不可用：{exc}"}
        item_evidence = [entry for entry in payload.get("evidence", []) if isinstance(entry, dict)]
        evidence.extend(item_evidence)
        evidence_by_item[item.ornament_id] = item_evidence
    narration = compose_guide_narration(program, evidence_by_item, detailed=detailed)
    source_text = "、".join(narration.source_ids) or "当前没有可引用的来源编号"
    message = narration.visitor_message + f"\n来源：{source_text}。"
    view = present_tour_state(tour_state, interaction_state, message=message)
    return {
        "message": message,
        "status": "guided" if evidence else "guided_without_evidence",
        "stop_program": program.to_dict(),
        "evidence": evidence,
        "evidence_by_item": evidence_by_item,
        "rag_queries": rag_queries,
        "source_ids": list(narration.source_ids),
        "narration": {
            "used_llm": narration.used_llm,
            "fallback_reason": narration.fallback_reason,
            "detailed": detailed,
        },
        "presentation": {**view, "code": "stop_guidance", "ok": True, "evidence_count": len(evidence)},
    }
