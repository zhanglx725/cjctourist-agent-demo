"""Deterministic, public-language routing for high-frequency visitor QA.

This module only classifies a visitor's stated purpose.  It does not retrieve
data, call a model, or mutate tour state.  Keeping these aliases in one place
prevents each answer path from drifting into a different interpretation of the
same everyday wording.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisitorQaIntent:
    """Read-only result used by FactCard and specialised QA dispatchers."""

    name: str
    fact_card_ids: tuple[str, ...] = ()
    requested_question_types: tuple[str, ...] = ()


_PHOTO_SPOT_CUES = (
    "哪里拍", "在哪拍", "拍哪里", "拍照点", "拍摄点", "机位", "取景",
    "打卡点", "出片", "构图", "姿势", "怎么摆", "怎么拍好看",
)

_FACT_CARD_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "opening_hours_regular",
        ("营业时间", "开放时间", "开门时间", "关门时间", "几点开门", "几点关门", "闭馆", "几点能进", "早上", "能进园", "能进去"),
    ),
    (
        "transport_metro_arrival",
        ("公共交通", "地铁", "坐什么车", "公交怎么去", "怎么坐地铁", "怎么过来", "怎么去", "怎么到", "交通方式"),
    ),
    (
        "ticketing_purchase_method",
        ("怎么购票", "怎么买票", "学生票怎么买", "如何购票", "购票方式", "购票方法", "当天买票", "当天能买票", "还能买票", "买票进去", "预约购票"),
    ),
    (
        "ticketing_individual_refund",
        ("退票", "退款", "能退吗", "可以退吗"),
    ),
    (
        "visit_service_photo_rule",
        ("可以拍照", "能拍照", "允许拍照", "拍照规定", "拍照规则", "闪光灯", "商业拍摄", "商业摄影", "三脚架"),
    ),
    (
        "visit_service_luggage_storage",
        ("行李寄存", "寄存行李", "存包", "寄存", "行李"),
    ),
    (
        "visit_service_free_guidance",
        ("免费讲解", "人工讲解", "有讲解吗", "讲解时间", "讲解几点"),
    ),
)

_REFUND_EXCLUSIONS = ("发票", "团体", "团队")
_CARD_REQUEST_TYPES = {
    "opening_hours_regular": ("time", "availability"),
    "transport_metro_arrival": ("method", "location"),
    "ticketing_purchase_method": ("method",),
    "ticketing_individual_refund": ("rule", "method"),
    "visit_service_photo_rule": ("rule", "availability"),
    "visit_service_luggage_storage": ("availability", "method"),
    "visit_service_free_guidance": ("availability", "method"),
}
_NEARBY_CONTEXT_CUES = ("周边", "附近", "馆外", "陈家祠外", "参观完", "游览完", "逛完", "离开后", "接下来去哪", "接着去哪")
_NEARBY_FOOD_CUES = ("吃饭", "吃什么", "好吃", "餐厅", "餐馆", "饭店", "美食", "小吃", "咖啡", "喝茶", "早茶", "奶茶", "甜品", "糖水", "面食", "面馆")
_NEARBY_SIGHT_CUES = ("逛", "可逛", "景点", "游玩", "玩的地方", "博物馆", "展览", "公园", "历史文化")
_NEARBY_GENERAL_CUES = ("休息", "歇脚", "手信", "伴手礼", "购物", "店", "去哪里", "推荐")


def classify_visitor_qa_intent(user_text: str) -> VisitorQaIntent:
    """Classify supported service questions without broad keyword capture.

    A request for photo locations is deliberately never converted into a
    photo-rule answer.  Invoice and group-ticket wording is likewise left to
    the existing controlled ticketing plan, which can answer the compound
    request safely.
    """

    text = str(user_text or "")
    if any(cue in text for cue in _PHOTO_SPOT_CUES):
        return VisitorQaIntent("photo_spot")

    card_ids: list[str] = []
    for card_id, cues in _FACT_CARD_CUES:
        if not any(cue in text for cue in cues):
            continue
        if card_id == "ticketing_individual_refund" and any(cue in text for cue in _REFUND_EXCLUSIONS):
            continue
        card_ids.append(card_id)

    if card_ids:
        requested = [kind for card_id in card_ids for kind in _CARD_REQUEST_TYPES[card_id]]
        # These are distinct sub-questions with no reviewed card in the first
        # batch.  Keep the confirmed answer and make the coverage gap visible.
        if any(cue in text for cue in ("学生票", "学生证")):
            requested.append("eligibility")
        if any(cue in text for cue in ("当天", "今天", "库存", "余票")):
            requested.append("availability")
        if any(cue in text for cue in ("来得及", "够不够时间", "逛完")):
            requested.append("recommendation")
        return VisitorQaIntent("fact_card", tuple(card_ids), tuple(dict.fromkeys(requested)))
    if any(cue in text for cue in _NEARBY_CONTEXT_CUES):
        if any(cue in text for cue in _NEARBY_FOOD_CUES):
            return VisitorQaIntent("nearby_food")
        if any(cue in text for cue in _NEARBY_SIGHT_CUES):
            return VisitorQaIntent("nearby_attraction")
        if any(cue in text for cue in _NEARBY_GENERAL_CUES):
            return VisitorQaIntent("nearby_general")
    return VisitorQaIntent("other")


def is_nearby_visitor_intent(user_text: str) -> bool:
    """Return whether public-language routing recognises an off-site request."""

    return classify_visitor_qa_intent(user_text).name in {"nearby_food", "nearby_attraction", "nearby_general"}


__all__ = ["VisitorQaIntent", "classify_visitor_qa_intent", "is_nearby_visitor_intent"]
