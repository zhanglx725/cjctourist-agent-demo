"""Deterministic P4-04 nearby-POI recommendations from the approved catalog.

The runtime is deliberately read-only.  It cannot add an outdoor POI to the
indoor route and never writes TourState, VisitorProfile, or Coverage.  URLs and
catalog identifiers remain internal; only reviewed public fields are rendered.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

import yaml


CATALOG_FILE = (
    Path(__file__).parent
    / "data" / "chen_clan_academy" / "evaluation" / "manual_reviews"
    / "p4_04_nearby_poi_card_authoring_template_v1.yaml"
)
EXPECTED_SCHEMA = "nearby_poi_card_authoring_v1"
PUBLIC_UNCERTAINTY = (
    "营业、价格、排队和交通信息可能变化，出发前请以场所官方页面或地图的最新信息为准。"
)
POST_VISIT_NEARBY_PROMPT = "请问您是否需要我为您推荐一些周边的美食？"
NEARBY_CUES = (
    "周边", "附近", "馆外", "陈家祠外", "参观完", "游览完", "结束后",
    "逛完", "离开后", "接下来去哪", "接着去哪",
)
PURPOSE_CUES = (
    "吃饭", "吃什么", "好吃", "餐厅", "餐馆", "饭店", "美食", "小吃", "咖啡", "喝茶", "奶茶", "甜品", "糖水", "面食", "面馆",
    "休息", "歇脚", "手信", "伴手礼", "购物", "店", "去哪里", "推荐",
)
ROUTE_CHANGE_CUES = ("加入路线", "加入行程", "改路线", "调整路线", "顺路安排")
PROHIBITED_PUBLIC_CLAIMS = (
    "最好", "第一", "必去", "必吃", "绝对", "保证营业", "绝对不排队", "最值得",
)
OFFER_ACCEPT = frozenset({
    "需要", "要", "可以", "好", "好的", "好啊", "可以啊", "需要的", "要的",
    "麻烦推荐", "推荐一下", "请推荐", "来一些", "想要",
})
OFFER_DECLINE = frozenset({
    "不需要", "不用", "不要", "算了", "暂时不用", "先不用", "不用了", "不了",
})
SUBTYPE_CUES = {
    "milk_tea": ("奶茶", "茶饮"),
    "coffee": ("咖啡",),
    "dessert": ("甜品", "糖水", "蛋糕", "烘焙", "西饼", "冰淇淋"),
    "noodles": ("面食", "面馆", "小面", "馄饨", "馄炖", "拉面"),
    "snacks": ("小吃", "零食", "煎饺", "牛杂", "章鱼小丸子"),
    "local_food": ("本地美食", "广州美食", "粤菜", "老字号"),
    "souvenir": ("手信", "伴手礼"),
}

CATEGORY_LABELS = {
    "food": "餐饮",
    "cafe_or_rest": "咖啡、茶饮或休息",
    "heritage_site": "历史文化场所",
    "museum_or_gallery": "博物馆或展览空间",
    "park_or_public_space": "公园或公共空间",
    "shopping_or_craft": "手信、购物或工艺",
    "hotel_or_accommodation_area": "住宿区域",
    "transport_or_visitor_service": "交通或游客服务",
}
CATEGORY_RATIONALES = {
    "food": "可作为参观结束后的餐饮候选。",
    "cafe_or_rest": "可作为参观结束后喝饮品或短暂休息的候选。",
    "heritage_site": "可作为继续了解本地历史文化的馆外候选。",
    "museum_or_gallery": "可作为继续参观文化展览的候选。",
    "park_or_public_space": "可作为馆外散步或休息的候选。",
    "shopping_or_craft": "可作为选购手信、食品或工艺商品的候选。",
    "hotel_or_accommodation_area": "可作为住宿区域信息参考。",
    "transport_or_visitor_service": "可作为后续交通或游客服务参考。",
}


def _repair_legacy_text(value: Any) -> str:
    """Repair the catalog's historical GBK-as-Latin-1 text without guessing.

    Already-correct Chinese and ASCII are returned unchanged.  The conversion
    is attempted only when every character can be represented as Latin-1 and
    the decoded result contains CJK text.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        repaired = text.encode("latin1").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if re.search(r"[\u3400-\u9fff]", repaired) else text


def is_explicit_nearby_request(user_query: str) -> bool:
    text = str(user_query or "")
    return (
        any(cue in text for cue in NEARBY_CUES)
        and any(cue in text for cue in PURPOSE_CUES)
    )


def classify_nearby_offer_response(user_query: str) -> str | None:
    compact = re.sub(r"[\s，。！？!?、,.]", "", str(user_query or ""))
    if compact in OFFER_DECLINE:
        return "decline"
    if compact in OFFER_ACCEPT:
        return "accept"
    return None


def requested_nearby_subtype(user_query: str) -> str | None:
    text = str(user_query or "")
    matched = [
        subtype for subtype, cues in SUBTYPE_CUES.items()
        if any(cue in text for cue in cues)
    ]
    return matched[0] if len(matched) == 1 else None


def is_nearby_offer_input(user_query: str, *, offer_pending: bool) -> bool:
    if is_explicit_nearby_request(user_query):
        return True
    if not offer_pending:
        return False
    return (
        classify_nearby_offer_response(user_query) is not None
        or requested_nearby_subtype(user_query) is not None
    )


def has_nearby_route_conflict(user_query: str) -> bool:
    text = str(user_query or "")
    route_mutation = any(cue in text for cue in ROUTE_CHANGE_CUES) or bool(
        re.search(r"(?:加入|加到|放进|安排进|添加到).{0,8}(?:路线|行程)", text)
    )
    return is_explicit_nearby_request(text) and route_mutation


def _requested_categories(text: str) -> set[str]:
    categories: set[str] = set()
    if any(cue in text for cue in ("吃饭", "吃什么", "好吃", "餐厅", "餐馆", "饭店", "美食", "小吃", "面食", "面馆")):
        categories.add("food")
    if any(cue in text for cue in ("咖啡", "喝茶", "奶茶", "茶饮", "甜品", "糖水", "休息", "歇脚")):
        categories.add("cafe_or_rest")
    if any(cue in text for cue in ("手信", "伴手礼", "购物")):
        categories.add("shopping_or_craft")
    return categories


def _requested_tags(text: str) -> set[str]:
    mapping = {
        "本地": "local_food", "广州": "local_food", "粤菜": "cantonese_food",
        "咖啡": "tea_or_coffee", "喝茶": "tea_or_coffee", "茶饮": "tea_or_coffee",
        "休息": "short_stop", "歇脚": "short_stop", "手信": "shopping",
        "伴手礼": "shopping",
    }
    return {tag for cue, tag in mapping.items() if cue in text}


def _valid_source(card: dict[str, Any]) -> bool:
    return any(
        str(card.get(field) or "").strip().startswith(("https://", "http://"))
        for field in ("evidence_url", "map_url")
    )


def _card_subtypes(name: str, category: str, raw_tags: tuple[str, ...]) -> tuple[str, ...]:
    value = name.lower()
    subtypes: set[str] = set()
    if any(term in value for term in ("茶饮", "說茶", "潮茶", "1点点", "鸳鸯王")):
        subtypes.add("milk_tea")
    if any(term in value for term in ("cafe", "coffee", "咖啡", "瑞幸", "铝咖")):
        subtypes.add("coffee")
    if any(term in value for term in ("甜品", "糖水", "蛋糕", "烘焙", "西饼", "冰淇淋")):
        subtypes.add("dessert")
    if any(term in value for term in ("小面", "面馆", "馄饨", "馄炖", "拉面")):
        subtypes.add("noodles")
    if any(term in value for term in ("零食", "煎饺", "牛杂", "章鱼小丸子")) or "snack" in raw_tags:
        subtypes.add("snacks")
    if "local_food" in raw_tags:
        subtypes.add("local_food")
    if category == "shopping_or_craft":
        subtypes.add("souvenir")
    return tuple(sorted(subtypes))


@lru_cache(maxsize=1)
def load_approved_nearby_pois(path: Path = CATALOG_FILE) -> tuple[dict[str, Any], ...]:
    """Load only reviewed runtime candidates and fail closed per card."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ()
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        return ()
    policy = payload.get("catalog_policy") or {}
    allowed_categories = set(policy.get("allowed_categories") or CATEGORY_LABELS)
    controlled_tags = set(payload.get("controlled_tags") or [])
    approved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in payload.get("cards") or []:
        if not isinstance(raw, dict):
            continue
        review = raw.get("review") or {}
        poi_id = str(raw.get("poi_id") or "").strip()
        category = str(raw.get("category") or "").strip()
        name = _repair_legacy_text(raw.get("name_zh"))
        address = _repair_legacy_text(raw.get("address_zh"))
        address = re.sub(r"[（(][^）)]*步行[^）)]*[）)]", "", address).strip()
        raw_tags = tuple(str(item) for item in raw.get("tags") or [] if isinstance(item, str))
        tags = tuple(
            str(item) for item in raw.get("tags") or []
            if isinstance(item, str) and item in controlled_tags
        )
        if (
            not poi_id or poi_id in seen_ids or not name or not address
            or raw.get("decision") != "approve"
            or review.get("status") != "approved"
            or raw.get("enabled") is not True
            or category not in allowed_categories
            or not tags
            or not _valid_source(raw)
        ):
            continue
        summary = _repair_legacy_text(raw.get("one_line_summary_zh"))
        reason = _repair_legacy_text(raw.get("why_recommend_zh"))
        if any(term in summary or term in reason for term in PROHIBITED_PUBLIC_CLAIMS):
            continue
        walk_minutes = raw.get("walk_minutes_from_chen_clan_academy")
        approved.append({
            "poi_id": poi_id,
            "name_zh": name,
            "address_zh": address,
            "category": category,
            "tags": tags,
            "subtypes": _card_subtypes(name, category, raw_tags),
            # These two fields are authored and approved in the manual-review
            # catalog. Runtime still rejects prohibited superlatives above.
            "one_line_summary_zh": summary,
            "why_recommend_zh": reason,
            # This field is a ranking hint only and is never rendered as a
            # promised walking time.
            "distance_rank": walk_minutes if isinstance(walk_minutes, int) else 999,
        })
        seen_ids.add(poi_id)
    return tuple(approved)


def _sort_key(
    card: dict[str, Any], requested_categories: set[str], requested_tags: set[str],
) -> tuple[int, int, int, str]:
    category_priority = 0 if not requested_categories or card["category"] in requested_categories else 1
    tag_priority = -len(set(card["tags"]).intersection(requested_tags))
    return category_priority, tag_priority, card["distance_rank"], card["poi_id"]


def _diversified_selection(cards: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for category in ("food", "cafe_or_rest", "shopping_or_craft"):
        candidate = next((card for card in cards if card["category"] == category), None)
        if candidate is not None:
            selected.append(candidate)
        if len(selected) == limit:
            break
    if len(selected) < limit:
        selected_ids = {card["poi_id"] for card in selected}
        selected.extend(card for card in cards if card["poi_id"] not in selected_ids)
    return selected[:limit]


def _render_card(card: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    label = CATEGORY_LABELS.get(card["category"], "周边场所")
    lines = [
        f"{card['name_zh']}（{label}）",
        f"地址：{card['address_zh']}",
    ]
    summary = str(card.get("one_line_summary_zh") or "").strip()
    reason = str(card.get("why_recommend_zh") or "").strip()
    if summary:
        lines.append(f"特色：{summary}")
    if reason:
        lines.append(f"推荐理由：{reason}")
    else:
        lines.append(CATEGORY_RATIONALES.get(card["category"], "可作为馆外周边参考。"))
    public_record = {
        "name_zh": card["name_zh"],
        "category": card["category"],
        "address_zh": card["address_zh"],
    }
    return "\n".join(lines), public_record


def answer_nearby_request(
    user_query: str,
    *,
    offer_pending: bool = False,
    excluded_poi_ids: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """Render up to three deterministic, reviewed outdoor recommendations."""
    response = classify_nearby_offer_response(user_query) if offer_pending else None
    if response == "decline":
        return {
            "message": "好的，本次不再推荐周边美食。祝您接下来的行程愉快！",
            "mode": "nearby_offer_declined",
            "nearby_pois": [],
            "selected_poi_ids": [],
            "offer_status": "declined",
        }
    if has_nearby_route_conflict(user_query):
        return {
            "message": (
                "周边推荐与修改馆内路线需要分别确认。本次只提供馆外参考，"
                "不会把周边地点加入陈家祠游览路线。\n\n" + PUBLIC_UNCERTAINTY
            ),
            "mode": "nearby_route_clarification",
            "nearby_pois": [],
            "selected_poi_ids": [],
            "offer_status": "awaiting_choice" if offer_pending else None,
        }
    cards = load_approved_nearby_pois()
    if not cards:
        return {
            "message": "当前没有可用的周边推荐。" + PUBLIC_UNCERTAINTY,
            "mode": "nearby_unavailable",
            "nearby_pois": [],
            "selected_poi_ids": [],
        }
    categories = _requested_categories(user_query)
    tags = _requested_tags(user_query)
    ranked = sorted(cards, key=lambda card: _sort_key(card, categories, tags))
    subtype = requested_nearby_subtype(user_query)
    if subtype:
        subtype_matches = [card for card in ranked if subtype in card.get("subtypes", ())]
        if subtype_matches:
            ranked = subtype_matches
    elif categories:
        matched = [card for card in ranked if card["category"] in categories]
        ranked = matched or ranked
    excluded = set(excluded_poi_ids)
    remaining = [card for card in ranked if card["poi_id"] not in excluded]
    if not remaining:
        return {
            "message": "这一类别中当前可用的选择已经全部为您展示完毕。您也可以换一种美食或饮品类型。",
            "mode": "nearby_candidates_exhausted",
            "nearby_pois": [],
            "selected_poi_ids": [],
            "offer_status": "completed",
        }
    selected = _diversified_selection(remaining) if response == "accept" else remaining[:3]
    rendered = [_render_card(card) for card in selected]
    return {
        "message": (
            "可以参考以下周边选择：\n\n"
            + "\n\n".join(text for text, _ in rendered)
            + "\n\n" + PUBLIC_UNCERTAINTY
        ),
        "mode": "nearby_recommendation",
        "nearby_pois": [record for _, record in rendered],
        "selected_poi_ids": [card["poi_id"] for card in selected],
        "offer_status": "completed",
    }
