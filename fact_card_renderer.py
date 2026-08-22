"""Deterministic public rendering for reviewed :mod:`fact_card_contract` cards.

This module is the common renderer used by later opening-hours, transport,
ticketing, service, and nearby-card migrations.  It intentionally receives
already selected cards and never retrieves facts, invokes a model, or writes
agent state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from fact_card_contract import FACT_CARD_QUESTION_TYPES, FactCard


_TEMPLATE_HEADINGS = {
    "time_window": "开放与入馆",
    "transport_options": "交通出行",
    "service_rule": "现场规则",
    "service_steps": "现场服务",
    "ticketing_rule": "票务规则",
    "ticketing_method": "购票与预约",
    "nearby_candidates": "周边参考",
}
_PARTIAL_NOTICE_PREFIX = "以上是现有公开资料能够确认的部分；"
_PUBLIC_QUESTION_TYPE_LABELS = {
    "time": "特定日期或时段安排",
    "availability": "当天可用性、余票或现场服务情况",
    "method": "具体办理方式",
    "rule": "适用规则",
    "eligibility": "优惠资格或所需证件",
    "location": "精确地点",
    "recommendation": "实际游览时长或个性化安排",
}
_NO_MATCH_MESSAGE = "当前没有可确认的公开资料可直接回答这个问题。"


@dataclass(frozen=True)
class FactCardAnswer:
    """Public text plus a structured audit of complete or partial coverage."""

    message: str
    status: str
    answered_card_ids: tuple[str, ...]
    answered_question_types: tuple[str, ...]
    unanswered_question_types: tuple[str, ...]
    partial: bool

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "answered_card_ids", "answered_question_types", "unanswered_question_types",
        ):
            result[key] = list(result[key])
        return result


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _partial_notice(unanswered_question_types: Iterable[str]) -> str:
    labels = _dedupe(_PUBLIC_QUESTION_TYPE_LABELS[kind] for kind in unanswered_question_types)
    if not labels:
        return _PARTIAL_NOTICE_PREFIX
    return (
        f"{_PARTIAL_NOTICE_PREFIX}“{'、'.join(labels)}”暂未得到足够的已核验信息，"
        "请以馆方当日公告或现场指引为准。"
    )


def render_fact_cards(
    cards: Iterable[FactCard],
    *,
    requested_question_types: Iterable[str] = (),
) -> FactCardAnswer:
    """Render enabled cards using their reviewed public fields only.

    ``requested_question_types`` is optional for a one-card question.  For a
    composite question, omitted types produce a *partial* public answer rather
    than discarding the confirmed cards.  Callers remain responsible for
    selecting cards whose trigger and applicability conditions match the
    visitor's utterance.
    """

    requested = _dedupe(str(kind).strip() for kind in requested_question_types)
    if not set(requested).issubset(FACT_CARD_QUESTION_TYPES):
        raise ValueError("requested_question_types contains an unknown type")
    selected = tuple(card for card in cards if isinstance(card, FactCard) and card.runtime_status == "enabled")
    if not selected:
        return FactCardAnswer(
            message=_NO_MATCH_MESSAGE,
            status="no_matching_card",
            answered_card_ids=(),
            answered_question_types=(),
            unanswered_question_types=requested,
            partial=False,
        )

    sections: list[str] = []
    notices: list[str] = []
    answered_types: list[str] = []
    answered_ids: list[str] = []
    for card in selected:
        heading = _TEMPLATE_HEADINGS[card.public_template_id]
        lines = [f"{heading}：", *card.fact_statements]
        if card.applicability_conditions:
            lines.append("适用说明：" + "；".join(card.applicability_conditions))
        sections.append("\n".join(lines))
        answered_ids.append(card.card_id)
        answered_types.extend(card.question_types)
        if card.freshness_notice:
            notices.append(card.freshness_notice)

    answered = _dedupe(answered_types)
    unanswered = tuple(kind for kind in requested if kind not in answered)
    partial = bool(unanswered)
    if partial:
        sections.append(_partial_notice(unanswered))
    if notices:
        sections.append("\n".join(_dedupe(notices)))
    return FactCardAnswer(
        message="\n\n".join(sections),
        status="partial" if partial else "complete",
        answered_card_ids=_dedupe(answered_ids),
        answered_question_types=answered,
        unanswered_question_types=unanswered,
        partial=partial,
    )


__all__ = ["FactCardAnswer", "render_fact_cards"]
