"""CA-04 read-only adapters for the remaining reviewed content backends.

These functions intentionally accept resolver output/evidence from their caller.
They do not identify IDs, write visitor state, or change graph routing.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from comparison_retrieval import format_gated_comparison_answer, retrieve_gated_comparison
from controlled_knowledge_query import public_visitor_message_or_fallback
from craft_knowledge import (
    CraftKnowledgeError,
    load_craft_record,
    parse_craft_explanation_request,
    parse_craft_location_request,
    render_craft_explanation,
    render_craft_location_answer,
)
from ornament_detail_runtime import (
    build_object_evidence_view,
    filter_object_evidence,
    render_object_detail,
)
from research_card_retrieval import format_research_answer, retrieve_research_cards
from reviewed_read_tools import ReadToolResult
from tour_qa import format_point_inventory


def _result(capability: str, status: str, message: str, evidence: Iterable[Mapping[str, Any]] = (), **audit: Any) -> ReadToolResult:
    return ReadToolResult(
        capability=capability,
        status=status,
        message=public_visitor_message_or_fallback(message),
        evidence=tuple(dict(item) for item in evidence if isinstance(item, Mapping)),
        audit=audit,
    )


def answer_reviewed_craft(user_text: str) -> ReadToolResult:
    """Answer only a recognized canonical craft request or location list."""
    location_request = parse_craft_location_request(user_text)
    if location_request is not None:
        answer = render_craft_location_answer(location_request)
        return _result(
            "craft", "partial" if answer.missing_crafts else "ok", answer.message, answer.evidence,
            crafts=list(location_request.crafts), missing_crafts=list(answer.missing_crafts),
            retrieval_strategy="canonical_craft_location_fields",
        )
    request = parse_craft_explanation_request(user_text)
    if request is None:
        return _result("craft", "not_eligible", "当前问题不属于可安全匹配的已审核工艺讲解范围，因此不作推测。", retrieval_strategy=None)
    try:
        record = load_craft_record(request.craft)
    except CraftKnowledgeError:
        return _result("craft", "insufficient_evidence", "现有审核资料不足以安全说明这项工艺，因此不作推测。", craft=request.craft, retrieval_strategy="canonical_craft_section")
    evidence = record.to_evidence()
    return _result(
        "craft", "ok", render_craft_explanation(record, request.detail_level), (evidence,),
        craft=request.craft, detail_level=request.detail_level, source_ids=list(record.source_ids),
        retrieval_strategy="canonical_craft_section",
    )


def answer_reviewed_object(
    resolved_object: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]], *, detailed: bool = False,
) -> ReadToolResult:
    """Render one resolver-supplied object using only exact item evidence."""
    required = ("ornament_id", "name", "craft", "node_id")
    if not all(isinstance(resolved_object.get(key), str) and resolved_object[key].strip() for key in required):
        return _result("object", "not_eligible", "当前没有可核对的已审核对象，因此不会猜测对象详情。", retrieval_strategy=None)
    accepted = filter_object_evidence(
        ornament_id=resolved_object["ornament_id"], name=resolved_object["name"], craft=resolved_object["craft"],
        node_id=resolved_object["node_id"], evidence=evidence, strict_identity=True,
    )
    if not accepted:
        return _result(
            "object", "insufficient_evidence", "现有资料不足以安全说明这件对象的详情，因此不作推测。", (),
            ornament_id=resolved_object["ornament_id"], node_id=resolved_object["node_id"],
            retrieval_strategy="reviewed_ornament_exact_evidence",
        )
    view = build_object_evidence_view(
        ornament_id=resolved_object["ornament_id"], name=resolved_object["name"], craft=resolved_object["craft"],
        node_id=resolved_object["node_id"], raw_location=resolved_object.get("raw_location"),
        evidence=accepted, strict_identity=True,
    )
    rendered = render_object_detail(view, first=True, detailed=detailed)
    return _result(
        "object", "ok" if rendered.coverage_level != "insufficient" else "insufficient_evidence", rendered.visitor_text,
        accepted, ornament_id=view.ornament_id, node_id=view.node_id, craft=view.craft,
        source_ids=list(rendered.source_ids), coverage_level=rendered.coverage_level,
        retrieval_strategy="reviewed_ornament_exact_evidence",
    )


def answer_reviewed_point_inventory(
    user_text: str, tour_state: Mapping[str, Any] | None, interaction_state: Mapping[str, Any] | None,
    *, formatter: Callable[..., dict[str, Any]] = format_point_inventory,
) -> ReadToolResult:
    """Expose the existing immutable point inventory formatter as an adapter."""
    response = formatter(user_text, dict(tour_state) if tour_state else None, dict(interaction_state) if interaction_state else None)
    inventory = response.get("inventory") if isinstance(response, Mapping) else None
    status = "ok" if inventory else ("not_eligible" if response.get("mode") == "not_inventory" else "insufficient_evidence")
    return _result("point_inventory", status, str(response.get("message") or ""), (), inventory=inventory, mode=response.get("mode"), retrieval_strategy="reviewed_point_inventory")


def answer_reviewed_research(user_text: str, *, current_node_id: str | None = None, knowledge_level: str = "general", retriever: Callable[..., dict[str, Any]] = retrieve_research_cards) -> ReadToolResult:
    """Return only an explicitly eligible attributed research-card response."""
    context = retriever(user_text, current_node_id=current_node_id)
    status = "ok" if context.get("status") == "ok" else "insufficient_evidence"
    return _result("research", status, format_research_answer(context, knowledge_level=knowledge_level), (), research_status=context.get("status"), retrieval_strategy="attributed_research_card")


def answer_reviewed_comparison(user_text: str, *, allow_research: bool, retriever: Callable[..., dict[str, Any]] = retrieve_gated_comparison) -> ReadToolResult:
    """Return a comparison only when its existing card gate accepts both sides."""
    context = retriever(user_text, allow_research=allow_research)
    status = "ok" if context.get("status") == "ok" else "not_eligible"
    return _result("comparison", status, format_gated_comparison_answer(context), (), comparison_status=context.get("status"), retrieval_strategy="attributed_comparison_card")
