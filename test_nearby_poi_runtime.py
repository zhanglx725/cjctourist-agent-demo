"""P4-04 deterministic nearby-POI runtime tests."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from nearby_poi_runtime import (
    PUBLIC_UNCERTAINTY,
    answer_nearby_request,
    classify_nearby_offer_response,
    has_nearby_route_conflict,
    is_explicit_nearby_request,
    load_approved_nearby_pois,
)


def _cards() -> tuple[dict, ...]:
    return (
        {"poi_id": "poi_food", "name_zh": "审核面食候选", "address_zh": "示例路一号", "category": "food", "tags": ("local_food",), "subtypes": ("noodles", "local_food"), "one_line_summary_zh": "一处经过审核的餐饮候选。", "why_recommend_zh": "可作为参观后的餐饮参考。", "distance_rank": 4},
        {"poi_id": "poi_cafe", "name_zh": "审核奶茶候选", "address_zh": "示例路二号", "category": "cafe_or_rest", "tags": ("tea_or_coffee", "short_stop"), "subtypes": ("milk_tea",), "one_line_summary_zh": "一处经过审核的休息候选。", "why_recommend_zh": "可作为参观后的短暂停留参考。", "distance_rank": 2},
        {"poi_id": "poi_shop", "name_zh": "审核手信候选", "address_zh": "示例路三号", "category": "shopping_or_craft", "tags": ("shopping",), "subtypes": ("souvenir",), "one_line_summary_zh": "", "why_recommend_zh": "", "distance_rank": 3},
    )


class NearbyPoiRuntimeTests(unittest.TestCase):
    def test_real_catalog_loads_approved_enabled_cards_and_repairs_text(self) -> None:
        cards = load_approved_nearby_pois()
        self.assertGreater(len(cards), 0)
        self.assertTrue(all(card["name_zh"] and card["address_zh"] for card in cards))
        self.assertTrue(any("利口福" in card["name_zh"] for card in cards))

    def test_intent_requires_nearby_context_and_purpose(self) -> None:
        self.assertTrue(is_explicit_nearby_request("陈家祠附近有什么吃饭的地方？"))
        self.assertTrue(is_explicit_nearby_request("参观完想找一家咖啡店休息"))
        self.assertTrue(is_explicit_nearby_request("馆外哪里可以买手信？"))
        self.assertFalse(is_explicit_nearby_request("陈家祠里面可以吃东西吗？"))
        self.assertFalse(is_explicit_nearby_request("灰塑附近有什么纹样？"))

    def test_requested_category_outranks_distance(self) -> None:
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            food = answer_nearby_request("附近有什么吃饭的地方？")
            rest = answer_nearby_request("参观完想找咖啡店休息")
            shopping = answer_nearby_request("馆外哪里可以买手信？")
        self.assertEqual(food["nearby_pois"][0]["name_zh"], "审核面食候选")
        self.assertEqual(rest["nearby_pois"][0]["name_zh"], "审核奶茶候选")
        self.assertEqual(shopping["nearby_pois"][0]["name_zh"], "审核手信候选")

    def test_guangdong_cuisine_request_requires_cantonese_evidence(self) -> None:
        cards = (
            {
                "poi_id": "hunan", "name_zh": "审核湘菜馆", "address_zh": "示例路一号",
                "category": "food", "tags": ("local_food",), "subtypes": ("local_food",),
                "one_line_summary_zh": "提供湖南风味菜肴。",
                "why_recommend_zh": "可作为参观后的餐饮参考。", "distance_rank": 1,
            },
            {
                "poi_id": "cantonese", "name_zh": "审核粤式餐厅", "address_zh": "示例路二号",
                "category": "food", "tags": ("local_food",), "subtypes": ("local_food",),
                "one_line_summary_zh": "提供粤式风味菜肴。",
                "why_recommend_zh": "可作为参观后的餐饮参考。", "distance_rank": 4,
            },
            {
                "poi_id": "beef_offal", "name_zh": "审核牛杂", "address_zh": "示例路三号",
                "category": "food", "tags": ("local_food",), "subtypes": ("local_food", "snacks"),
                "one_line_summary_zh": "广州特色牛杂小吃。",
                "why_recommend_zh": "可作为参观后的餐饮参考。", "distance_rank": 5,
            },
        )
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=cards):
            result = answer_nearby_request("周边有什么广东特色美食？")
        self.assertEqual(result["mode"], "nearby_recommendation")
        self.assertIn("广东特色美食", result["message"])
        self.assertEqual(
            [item["name_zh"] for item in result["nearby_pois"]],
            ["审核粤式餐厅", "审核牛杂"],
        )
        self.assertNotIn("审核湘菜馆", result["message"])

    def test_guangdong_cuisine_request_does_not_fall_back_to_other_cuisines(self) -> None:
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=(
            {
                "poi_id": "hunan", "name_zh": "审核湘菜馆", "address_zh": "示例路一号",
                "category": "food", "tags": ("local_food",), "subtypes": ("local_food",),
                "one_line_summary_zh": "提供湖南风味菜肴。",
                "why_recommend_zh": "可作为参观后的餐饮参考。", "distance_rank": 1,
            },
        )):
            result = answer_nearby_request("附近有什么粤菜？")
        self.assertEqual(result["mode"], "nearby_no_matching_cuisine")
        self.assertEqual(result["nearby_pois"], [])
        self.assertIn("不会用其他菜系替代", result["message"])

    def test_real_catalog_guangdong_cuisine_query_excludes_hunan_restaurant(self) -> None:
        result = answer_nearby_request("周边有什么广东特色美食？")
        self.assertEqual(result["mode"], "nearby_recommendation")
        self.assertNotIn("湘馆主", result["message"])
        self.assertTrue(result["nearby_pois"])

    def test_public_output_is_bounded_and_has_uncertainty(self) -> None:
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            result = answer_nearby_request("周边有什么推荐？")
        self.assertEqual(result["mode"], "nearby_recommendation")
        self.assertLessEqual(len(result["nearby_pois"]), 3)
        self.assertIn(PUBLIC_UNCERTAINTY, result["message"])
        for forbidden in ("poi_food", "http://", "https://", "source_id", "步行"):
            self.assertNotIn(forbidden, result["message"])

    def test_route_conflict_never_returns_a_candidate(self) -> None:
        text = "把附近咖啡店加入路线"
        self.assertTrue(has_nearby_route_conflict(text))
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            result = answer_nearby_request(text)
        self.assertEqual(result["mode"], "nearby_route_clarification")
        self.assertEqual(result["nearby_pois"], [])
        self.assertIn("不会把周边地点加入", result["message"])

    def test_runtime_is_read_only(self) -> None:
        tour = {"route_status": "touring", "current_stop_id": "label_moon_platform"}
        profile = {"interests": ["灰塑"]}
        before_tour, before_profile = deepcopy(tour), deepcopy(profile)
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            answer_nearby_request("附近哪里可以喝咖啡？")
        self.assertEqual(tour, before_tour)
        self.assertEqual(profile, before_profile)

    def test_reviewed_summary_and_reason_are_rendered(self) -> None:
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            result = answer_nearby_request("附近有什么奶茶？")
        self.assertIn("特色：一处经过审核的休息候选。", result["message"])
        self.assertIn("推荐理由：可作为参观后的短暂停留参考。", result["message"])

    def test_repeated_subtype_excludes_previous_candidates(self) -> None:
        cards = (*_cards(), {
            **_cards()[1], "poi_id": "poi_cafe_2",
            "name_zh": "第二家审核奶茶候选", "distance_rank": 5,
        })
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=cards):
            first = answer_nearby_request("附近有什么奶茶？")
            second = answer_nearby_request(
                "还有什么奶茶？", offer_pending=True,
                excluded_poi_ids=first["selected_poi_ids"],
            )
            exhausted = answer_nearby_request(
                "还有什么奶茶？", offer_pending=True,
                excluded_poi_ids=[*first["selected_poi_ids"], *second["selected_poi_ids"]],
            )
        self.assertNotEqual(first["selected_poi_ids"], second["selected_poi_ids"])
        self.assertEqual(exhausted["mode"], "nearby_candidates_exhausted")

    def test_natural_route_mutation_wording_is_clarified(self) -> None:
        text = "把附近的奶茶店加入我的游览路线。"
        self.assertTrue(has_nearby_route_conflict(text))
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            result = answer_nearby_request(text)
        self.assertEqual(result["mode"], "nearby_route_clarification")
        self.assertEqual(result["nearby_pois"], [])

    def test_pending_offer_accept_decline_and_subtype_are_deterministic(self) -> None:
        self.assertEqual(classify_nearby_offer_response("需要"), "accept")
        self.assertEqual(classify_nearby_offer_response("不用了"), "decline")
        with patch("nearby_poi_runtime.load_approved_nearby_pois", return_value=_cards()):
            accepted = answer_nearby_request("需要", offer_pending=True)
            milk_tea = answer_nearby_request("奶茶有啥", offer_pending=True)
            noodles = answer_nearby_request("面食有啥", offer_pending=True)
            declined = answer_nearby_request("不需要", offer_pending=True)
        self.assertEqual(
            {item["category"] for item in accepted["nearby_pois"]},
            {"food", "cafe_or_rest", "shopping_or_craft"},
        )
        self.assertEqual(milk_tea["nearby_pois"][0]["name_zh"], "审核奶茶候选")
        self.assertEqual(noodles["nearby_pois"][0]["name_zh"], "审核面食候选")
        self.assertEqual(declined["mode"], "nearby_offer_declined")
        self.assertEqual(declined["offer_status"], "declined")


if __name__ == "__main__":
    unittest.main()
