"""B3 evidence orchestration for one deterministic StopProgram.

This module reuses the existing RAG callable.  It does not create an index,
change a route, or write TourState; only the A1 interaction adapter may do
that.  Point-card data determines the approved objects to cover, while RAG
evidence is the sole source for cultural or craft facts in the output.
"""

from __future__ import annotations

from typing import Any, Callable

from guide_program_planner import SelectedItem, StopProgram, plan_stop_program
from guide_narration import compose_guide_narration
from guidance_evidence_bundle import build_guidance_evidence_bundle
from narration_coverage import load_narration_coverage
from narration_rendering import render_guidance_evidence
from guidance_policy import GuidancePolicy, build_guidance_policy
from tour_presenter import present_tour_state
from tour_qa import load_guide_cards, parse_rag_payload
from visitor_profile import VisitorProfileError, create_visitor_profile, profile_from_dict


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
    guidance_policy: GuidancePolicy,
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
        guidance_policy=guidance_policy,
    )


def reexpress_current_stop_guidance(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    current_program: dict[str, Any] | None,
    evidence_by_item: dict[str, list[dict[str, Any]]] | None,
    visitor_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """Re-render exactly the active program under a new C8 policy.

    This intentionally performs no candidate selection and no RAG call.  It
    preserves selected IDs, allocation and previously collected evidence; only
    visitor-facing organisation changes after an explicit request.
    """
    if not _is_active_planned_stop(tour_state, interaction_state) or not current_program:
        return {"ok": False, "message": "当前没有可按新方式重新讲解的已到达点位。"}
    assert tour_state is not None and interaction_state is not None
    if current_program.get("node_id") != tour_state.get("current_stop_id"):
        return {"ok": False, "message": "当前讲解包与所在点位不一致，未重新组织讲解。"}
    try:
        policy = _guidance_policy_for_tour(tour_state, visitor_profile)
        items = tuple(SelectedItem(**item) for item in current_program.get("selected_items", []))
        program = StopProgram(
            node_id=current_program["node_id"], display_name=current_program["display_name"],
            budget_seconds=current_program["budget_seconds"], interests=tuple(current_program.get("interests", [])),
            detail_level=current_program["detail_level"], selected_items=items,
            candidate_count=current_program["candidate_count"],
            budget_scope=current_program.get("budget_scope", "stop_explanation_content_only"),
            allocated_content_seconds=current_program.get("allocated_content_seconds", 0),
            unallocated_content_seconds=current_program.get("unallocated_content_seconds", 0),
            selection_strategy=current_program.get("selection_strategy", "b2_relevance_diversity_budget"),
            status=current_program.get("status", "ready"), guidance_policy=policy.to_dict(),
        )
    except (KeyError, TypeError, VisitorProfileError) as exc:
        return {"ok": False, "message": f"当前讲解包无法安全重新组织：{exc}"}
    values = evidence_by_item or {}
    narration = compose_guide_narration(program, values, detailed=False)
    message = narration.visitor_message + f"\n{_citation_text(narration.source_ids, policy)}"
    return {
        "ok": True, "message": message, "stop_program": program.to_dict(),
        "evidence_by_item": values,
        "evidence": [entry for entries in values.values() for entry in entries],
        "guidance_policy": policy.to_dict(),
        "presentation": {**present_tour_state(tour_state, interaction_state, message=message),
                         "code": "stop_guidance_reexpressed", "ok": True},
    }


def _guidance_policy_for_tour(
    tour_state: dict[str, Any], visitor_profile: dict[str, Any] | None
) -> GuidancePolicy:
    """Use the C5 profile when present, with a legacy TourState fallback.

    The fallback is ephemeral compatibility only: it reconstructs C5 neutral
    defaults from the already adopted TourState core fields and is never saved
    as a second profile or used to modify tour progress.
    """
    if visitor_profile is not None:
        return build_guidance_policy(profile_from_dict(visitor_profile))
    return build_guidance_policy(create_visitor_profile(
        available_minutes=tour_state["available_minutes"],
        interests=tour_state.get("interests", []),
        detail_level=tour_state.get("detail_level", "standard"),
    ))


def _citation_text(source_ids: tuple[str, ...], policy: GuidancePolicy) -> str:
    ids = "、".join(source_ids) or "当前没有可引用的来源编号"
    if policy.citation_detail == "detailed":
        return f"参考资料编号：{ids}（本地知识快照）"
    if policy.citation_detail == "standard":
        return f"参考来源：{ids}"
    return f"来源：{ids}"


def build_stop_guidance(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
    rag_search: Callable[[str], str],
    *,
    current_program: dict[str, Any] | None = None,
    detailed: bool = False,
    visitor_profile: dict[str, Any] | None = None,
    narration_coverage: dict[str, Any] | None = None,
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
    try:
        guidance_policy = _guidance_policy_for_tour(tour_state, visitor_profile)
    except VisitorProfileError as exc:
        message = f"当前导览偏好无效，无法安全生成个性化讲解：{exc}"
        return {
            "message": message,
            "status": "invalid_profile",
            "stop_program": None,
            "evidence": [],
            "rag_queries": [],
            "guidance_policy": None,
            "presentation": {**present_tour_state(tour_state, interaction_state), "message": message, "ok": False, "code": "guidance_invalid_profile"},
        }
    program = _program_from_state(tour_state, current_program, guidance_policy)
    if program is None:
        message = "当前点位缺少已审核的讲解内容预算或讲解包，无法安全生成本点讲解。"
        return {
            "message": message,
            "status": "program_unavailable",
            "stop_program": None,
            "evidence": [],
            "rag_queries": [],
            "guidance_policy": guidance_policy.to_dict(),
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
            "guidance_policy": guidance_policy.to_dict(),
            "presentation": {**present_tour_state(tour_state, interaction_state), "message": message, "code": "guidance_no_candidates", "ok": True},
        }

    # E5-A4 first attempts the typed evidence/rendering path.  It stays here,
    # before the legacy B3 loop, so a valid E5 answer does not duplicate RAG
    # calls.  Any bundle/rendering failure falls through to the established B3
    # behaviour and is deliberately ineligible for coverage submission.
    # ``request_stop_detail`` retains the established B3 expansion contract in
    # this increment.  E5-A4 only replaces the first-arrival presentation;
    # treating detail as E5 output now would silently drop the existing
    # detailed-answer behaviour before it has its own evidence contract.
    if not detailed:
        try:
            coverage = load_narration_coverage(narration_coverage)
            bundle = build_guidance_evidence_bundle(program, coverage, rag_search)
            render = render_guidance_evidence(program, bundle, guidance_policy)
            # A craft overview alone is not a complete stop-guidance answer:
            # E5's first-contact contract also requires a current reviewed
            # object with accepted 08 detail evidence.  Otherwise preserve the
            # established B3 object narration rather than replacing it with a
            # shallow craft-only message (and never submit coverage).
            if (
                render.visitor_message.strip()
                and render.used_source_ids
                and render.rendered_ornament_ids
                and bundle.ornament_details
            ):
                message = render.visitor_message
                view = present_tour_state(tour_state, interaction_state, message=message)
                e5_evidence = [
                    entry
                    for packet in (*bundle.craft_overviews.values(), *bundle.ornament_details.values())
                    for entry in packet.evidence
                ]
                return {
                    "message": message,
                    "status": "guided_e5",
                    "stop_program": program.to_dict(),
                    "evidence": [dict(entry) for entry in e5_evidence],
                    "evidence_by_item": bundle.evidence_by_item,
                    "rag_queries": [
                        packet.query
                        for packet in (*bundle.craft_overviews.values(), *bundle.ornament_details.values())
                    ],
                    "source_ids": list(render.used_source_ids),
                    "guidance_policy": guidance_policy.to_dict(),
                    "guidance_evidence_bundle_audit": {
                        "node_id": bundle.node_id,
                        "craft_ids": sorted(bundle.craft_overviews),
                        "ornament_ids": sorted(bundle.ornament_details),
                        "source_ids": list(bundle.source_ids),
                        "coverage_status": {kind: dict(values) for kind, values in bundle.coverage_status.items()},
                    },
                    "narration_render_audit": {
                        "node_id": bundle.node_id,
                        "rendered_craft_ids": list(render.rendered_craft_ids),
                        "rendered_ornament_ids": list(render.rendered_ornament_ids),
                        "used_source_ids": list(render.used_source_ids),
                        "content_budget_seconds": render.content_budget_seconds,
                        "allocated_content_seconds": render.allocated_content_seconds,
                    "omitted_ornament_ids": list(render.omitted_ornament_ids),
                    "warnings": list(render.warnings),
                    "style_id": render.style_id,
                    "style_schema_version": render.style_schema_version,
                    "style_fallback_used": render.style_fallback_used,
                    "style_warning_codes": list(render.style_warning_codes),
                },
                    "coverage_candidates": [candidate.to_dict() for candidate in render.eligible_coverage_candidates],
                    "narration": {"used_llm": False, "fallback_reason": None, "detailed": detailed, "renderer": "e5_a3"},
                    "presentation": {**view, "code": "stop_guidance", "ok": True, "evidence_count": len(e5_evidence)},
                }
        except Exception:
            # Existing B3 remains a safe presentation fallback.  Do not expose
            # a partial typed packet or submit a coverage candidate from this
            # path.
            pass

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
    message = narration.visitor_message + f"\n{_citation_text(narration.source_ids, guidance_policy)}。"
    view = present_tour_state(tour_state, interaction_state, message=message)
    return {
        "message": message,
        "status": "guided" if evidence else "guided_without_evidence",
        "stop_program": program.to_dict(),
        "evidence": evidence,
        "evidence_by_item": evidence_by_item,
        "rag_queries": rag_queries,
        "source_ids": list(narration.source_ids),
        "guidance_policy": guidance_policy.to_dict(),
        "narration": {
            "used_llm": narration.used_llm,
            "fallback_reason": narration.fallback_reason,
            "detailed": detailed,
            "renderer": "b3_legacy_fallback",
        },
        "presentation": {**view, "code": "stop_guidance", "ok": True, "evidence_count": len(evidence)},
    }
