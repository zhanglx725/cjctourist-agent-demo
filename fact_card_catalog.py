"""First reviewed FactCard batch for high-frequency visitor service QA.

Cards are authored from the existing reviewed knowledge snapshots.  Selection
uses the shared public-language intent router; rendering remains deterministic
and does not invoke retrieval or a model.
"""

from __future__ import annotations

from functools import lru_cache

from fact_card_contract import FactCard, FactCardCatalog
from fact_card_renderer import FactCardAnswer, render_fact_cards
from visitor_qa_intent import classify_visitor_qa_intent


@lru_cache(maxsize=1)
def load_high_frequency_fact_cards() -> FactCardCatalog:
    """Return the first P0, source-reviewed service fact-card batch."""

    return FactCardCatalog(cards=(
        FactCard(
            card_id="opening_hours_regular",
            domain="opening_hours",
            question_types=("time", "availability"),
            trigger_phrases=("营业时间", "开放时间", "几点开门", "几点关门", "能进去吗"),
            fact_statements=(
                "常规开放时间为 9:00 至 17:30。",
                "常规停止售票和停止入馆时间为 17:00。",
                "常规闭馆日为每周二，法定节假日除外。",
            ),
            applicability_conditions=("仅适用于常规开放安排。",),
            freshness_policy="dynamic",
            freshness_notice="节假日、恶劣天气、设备维护及临时活动可能调整开放安排，请以馆方当日公告为准。",
            public_template_id="time_window",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S01", "S03", "S04"),
            limitations=("不保证特定日期的临时开放或延时安排。",),
        ),
        FactCard(
            card_id="transport_metro_arrival",
            domain="transport",
            question_types=("method", "location"),
            trigger_phrases=("公共交通", "怎么坐地铁", "地铁怎么去", "怎么过来", "陈家祠站"),
            fact_statements=("可乘坐广州地铁 1 号线或 8 号线至陈家祠站，从 D/E 出口附近前往。",),
            applicability_conditions=("仅说明已核验的地铁到达方式。",),
            freshness_policy="static",
            freshness_notice=None,
            public_template_id="transport_options",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S05",),
            limitations=("公交、停车和无障碍到达信息未作为确定事实提供。",),
        ),
        FactCard(
            card_id="ticketing_purchase_method",
            domain="ticketing",
            question_types=("method",),
            trigger_phrases=("怎么购票", "怎么买票", "如何购票", "当天买票", "还能买票吗"),
            fact_statements=(
                "请通过微信公众号“广东民间工艺博物馆”服务号预约或购票。",
                "购票入口：https://wx.gzcjc.com.cn。",
            ),
            applicability_conditions=("仅说明已核验的官方预约和购票入口。",),
            freshness_policy="dynamic",
            freshness_notice="票价、场次、库存和开放安排可能调整，请以服务号或小程序当日页面为准。",
            public_template_id="ticketing_method",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S07",),
            limitations=("不保证特定日期仍有余票，也不替代优惠资格核验。",),
        ),
        FactCard(
            card_id="ticketing_individual_refund",
            domain="ticketing",
            question_types=("rule", "method"),
            trigger_phrases=("退票", "退款", "买了票能退吗", "门票能退吗"),
            fact_statements=(
                "未使用的散客门票可在参观当日 18:00 前，通过微信预约订单申请退票。",
                "每个订单仅可退款一次；部分退款后，该订单余款无法再次退款。",
            ),
            applicability_conditions=("仅适用于未使用的散客门票。",),
            freshness_policy="dynamic",
            freshness_notice="团队订单的退票规则不同，具体订单和当日规则请以官方小程序页面为准。",
            public_template_id="ticketing_rule",
            partial_answer_policy="clarify",
            source_refs=("S07",),
            limitations=("不判断具体订单是否符合退款条件。",),
        ),
        FactCard(
            card_id="visit_service_photo_rule",
            domain="visit_service",
            question_types=("rule", "availability"),
            trigger_phrases=("可以拍照吗", "能拍照吗", "拍照规定", "闪光灯", "商业拍摄"),
            fact_statements=(
                "室内对有玻璃罩的文物严禁使用闪光灯。",
                "商业拍摄需提前向馆方报备。",
            ),
            applicability_conditions=("仅说明资料明确列出的拍摄限制。",),
            freshness_policy="dynamic",
            freshness_notice="具体拍摄范围和现场管理要求可能调整，请以现场指引为准。",
            public_template_id="service_rule",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S03",),
            limitations=("不把拍照规则误作拍照点位推荐。",),
        ),
        FactCard(
            card_id="visit_service_luggage_storage",
            domain="visit_service",
            question_types=("availability", "method"),
            trigger_phrases=("行李寄存", "寄存行李", "存包", "能寄存吗"),
            fact_statements=("馆内提供小件物品寄存，但空间有限，不建议携带大型行李箱前往。",),
            applicability_conditions=("仅适用于馆内小件物品寄存服务。",),
            freshness_policy="dynamic",
            freshness_notice="寄存容量和现场安排可能调整，请以当日现场咨询为准。",
            public_template_id="service_steps",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S03",),
            limitations=("不承诺当日仍有可用寄存空间。",),
        ),
        FactCard(
            card_id="visit_service_free_guidance",
            domain="visit_service",
            question_types=("availability", "method"),
            trigger_phrases=("免费讲解", "人工讲解", "讲解时间", "有讲解吗"),
            fact_statements=("通常在 10:00 和 16:00 有定时免费讲解，可在正门集合点现场咨询预约。",),
            applicability_conditions=("仅适用于常规定时免费讲解。",),
            freshness_policy="dynamic",
            freshness_notice="节假日场次可能调整，请以当日现场公告或咨询结果为准。",
            public_template_id="service_steps",
            partial_answer_policy="answer_confirmed_portion",
            source_refs=("S03",),
            limitations=("不保证特定日期一定开设对应场次。",),
        ),
    ))


def answer_high_frequency_fact_cards(user_text: str) -> FactCardAnswer | None:
    """Select the first P0 cards from deterministic visitor-language cues."""

    intent = classify_visitor_qa_intent(user_text)
    if intent.name != "fact_card":
        return None
    # Keep the established controlled purchase flow authoritative for a
    # standalone purchase-method question.  The same reviewed purchase card
    # participates when it is one part of a composite request, where it lets
    # the renderer retain confirmed facts instead of rejecting the whole turn.
    if (
        intent.fact_card_ids == ("ticketing_purchase_method",)
        and intent.requested_question_types == ("method",)
    ):
        return None
    cards_by_id = {card.card_id: card for card in load_high_frequency_fact_cards().cards}
    selected = tuple(cards_by_id[card_id] for card_id in intent.fact_card_ids)
    return render_fact_cards(selected, requested_question_types=intent.requested_question_types)


__all__ = ["answer_high_frequency_fact_cards", "load_high_frequency_fact_cards"]
