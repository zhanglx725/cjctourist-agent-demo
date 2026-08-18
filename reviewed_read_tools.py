"""CA-03 adapters for existing reviewed read-only knowledge backends.

Adapters return a typed audit envelope without modifying route or profile state.
They accept evidence supplied by a later executor; they do not retrieve, route,
or manufacture facts themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from controlled_knowledge_query import (
    filter_plan_evidence,
    identify_controlled_knowledge_plan,
    public_visitor_message_or_fallback,
    render_controlled_knowledge_answer,
)
from single_fact_answer import (
    identify_single_fact_kind,
    is_identity_document_civil_service_request,
    render_identity_document_civil_service_boundary,
    render_single_fact_answer,
)
from term_card_runtime import answer_term_question


@dataclass(frozen=True)
class ReadToolResult:
    capability: str
    status: str
    message: str
    evidence: tuple[dict[str, Any], ...]
    audit: dict[str, Any]


def _result(
    capability: str,
    status: str,
    message: str,
    evidence: Iterable[dict[str, Any]] = (),
    **audit: Any,
) -> ReadToolResult:
    return ReadToolResult(
        capability=capability,
        status=status,
        message=public_visitor_message_or_fallback(message),
        evidence=tuple(dict(item) for item in evidence if isinstance(item, dict)),
        audit=audit,
    )


def answer_reviewed_single_fact(
    user_text: str,
    evidence: Iterable[dict[str, Any]],
) -> ReadToolResult:
    """Use the existing single-fact renderer with caller-supplied evidence only."""
    supplied = tuple(dict(item) for item in evidence if isinstance(item, dict))
    if is_identity_document_civil_service_request(user_text):
        return _result(
            "single_fact", "outside_venue_scope",
            render_identity_document_civil_service_boundary(user_text), supplied,
            fact_kind=None, retrieval_strategy="civil_service_boundary",
        )
    fact_kind = identify_single_fact_kind(user_text)
    if fact_kind is None:
        return _result(
            "single_fact", "not_eligible",
            "现有资料不能安全回答这个问题，我不会据此猜测补答。",
            supplied, fact_kind=None, retrieval_strategy=None,
        )
    rendered = render_single_fact_answer(user_text, list(supplied), fact_kind=fact_kind)
    if rendered is None:
        return _result(
            "single_fact", "not_eligible",
            "现有资料不足以安全确认这一事实，因此不作推测。",
            supplied, fact_kind=fact_kind, retrieval_strategy="single_fact",
        )
    return _result(
        "single_fact", "ok" if rendered.ok else "insufficient_evidence", rendered.message, supplied,
        fact_kind=rendered.fact_kind, source_ids=list(rendered.source_ids),
        evidence_indexes=list(rendered.evidence_indexes), evidence_categories=list(rendered.evidence_categories),
        calculation=rendered.calculation, retrieval_strategy="single_fact",
    )


def answer_reviewed_term(
    user_text: str,
    *,
    term_answerer: Callable[..., dict[str, Any] | None] = answer_term_question,
) -> ReadToolResult:
    """Expose an eligible term answer without passing mutable tour state."""
    answer = term_answerer(user_text, None, None)
    if not isinstance(answer, Mapping):
        return _result(
            "term", "not_eligible",
            "当前没有可安全输出的术语说明。",
            (), term=None, retrieval_strategy="term_runtime",
        )
    term = answer.get("term") if isinstance(answer.get("term"), Mapping) else None
    source_ids = list(term.get("source_ids", [])) if term else []
    return _result(
        "term", str(answer.get("mode") or "ok"), str(answer.get("message") or ""),
        answer.get("evidence") or (), term=dict(term) if term else None,
        term_instances=list(answer.get("term_instances") or ()), source_ids=source_ids,
        retrieval_strategy="term_runtime",
    )


def answer_reviewed_service_rule(
    user_text: str,
    evidence: Iterable[dict[str, Any]],
    *,
    invoke_model: Callable[[str], str],
) -> ReadToolResult:
    """Render only an eligible, category-scoped existing service-rule plan."""
    plan = identify_controlled_knowledge_plan(user_text)
    if plan is None or plan.domain not in {"visit_service", "ticketing", "event_notice"}:
        return _result(
            "visit_service", "not_eligible",
            "当前没有可安全匹配的参观服务规则，因此不作推测。",
            (), knowledge_plan=None, retrieval_strategy="controlled_knowledge",
        )
    supplied = tuple(dict(item) for item in evidence if isinstance(item, dict))
    scoped = filter_plan_evidence(plan, supplied)
    message = render_controlled_knowledge_answer(plan, scoped, invoke_model)
    return _result(
        "visit_service", "ok" if scoped else "insufficient_evidence", message, scoped,
        knowledge_plan=plan.to_dict(), source_ids=sorted({source for item in scoped for source in item.get("source_ids", [])}),
        retrieval_strategy="controlled_knowledge",
    )


def answer_reviewed_controlled_knowledge(
    user_text: str,
    evidence: Iterable[dict[str, Any]],
    *,
    invoke_model: Callable[[str], str],
) -> ReadToolResult:
    """Run the existing closed knowledge renderer through the CA-03 envelope.

    This deliberately reuses the legacy plan recognizer and renderer.  It is
    not a second knowledge source and accepts only caller-supplied evidence.
    """
    plan = identify_controlled_knowledge_plan(user_text)
    if plan is None:
        return _result(
            "controlled_knowledge", "not_eligible",
            "当前问题不属于可由受控知识通道安全回答的范围，因此不作推测。",
            (), knowledge_plan=None, retrieval_strategy="controlled_knowledge",
        )
    supplied = tuple(dict(item) for item in evidence if isinstance(item, dict))
    scoped = filter_plan_evidence(plan, supplied)
    message = render_controlled_knowledge_answer(plan, scoped, invoke_model)
    return _result(
        "controlled_knowledge", "ok" if scoped else "insufficient_evidence", message, scoped,
        knowledge_plan=plan.to_dict(),
        source_ids=sorted({source for item in scoped for source in item.get("source_ids", [])}),
        retrieval_strategy="controlled_knowledge",
    )
