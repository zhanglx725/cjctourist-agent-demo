"""Offline D6 selection tests; all inputs are injected D5 candidate results."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from photo_spot_runtime import (
    _candidate_sort_key,
    answer_photo_request,
    has_photo_route_conflict,
    is_explicit_photo_request,
    is_unsafe_photo_request,
)


CURRENT = "label_moon_platform"
NEXT = "stop_front_courtyard_center"
OTHER = "stop_rear_west_courtyard"


def _candidates() -> dict:
    return {
        "photo_current": {"available": True, "node_id": CURRENT, "pose_template_ids": ("pose_safe",), "limitations": ("不倚靠构件。",)},
        "photo_next": {"available": True, "node_id": NEXT, "pose_template_ids": ("pose_safe",), "limitations": ("不阻碍通行。",)},
        "photo_other": {"available": True, "node_id": OTHER, "pose_template_ids": ("pose_safe",), "limitations": ("不跨越围挡。",)},
        "photo_broken": {"available": False, "node_id": "bad", "pose_template_ids": (), "limitations": ()},
    }


def _selector(*, node_id: str, audience_mode=None, themes=()):
    del audience_mode
    spots = {
        CURRENT: ("月台构件层次", ["craft_detail", "openwork"], ["friends"]),
        NEXT: ("前院入口层次", ["architecture_signature", "portrait_memory"], ["family", "friends"]),
        OTHER: ("后部故事装饰", ["story_task", "three_kingdoms"], ["solo_travelers"]),
    }
    title, spot_themes, groups = spots[node_id]
    if themes and not set(themes).intersection(spot_themes):
        return {"available": False, "reason": "theme_not_matched"}
    return {
        "available": True,
        "photo_spot": {"title_zh": title, "node_id": node_id, "themes": spot_themes, "target_groups": groups},
        "pose_templates": [{"title_zh": "远观姿势", "instruction_zh": "在允许停留处自然站立。", "safety_boundary_zh": "不触摸构件。"}],
        "limitations": ["这是项目编辑整理的拍摄建议，具体可见性、光线、客流和开放情况请以现场为准。", "不阻碍通行。"],
    }


class PhotoSpotRuntimeTests(unittest.TestCase):
    def test_candidate_sort_key_explicitly_encodes_current_group_route_theme_and_id(self) -> None:
        """The final renderer receives a pre-ranked list, never dict order."""
        common = {
            "is_current_child": False,
            "themes": set(),
            "requested_themes": set(),
        }
        current = _candidate_sort_key(
            card_id="photo_current", node_id=CURRENT, current_node_id=CURRENT,
            target_groups=("friends",), group_hints=set(), remaining_rank={NEXT: 0, OTHER: 1}, **common,
        )
        next_key = _candidate_sort_key(
            card_id="photo_next", node_id=NEXT, current_node_id=CURRENT,
            target_groups=("family",), group_hints=set(), remaining_rank={NEXT: 0, OTHER: 1}, **common,
        )
        other = _candidate_sort_key(
            card_id="photo_other", node_id=OTHER, current_node_id=CURRENT,
            target_groups=("solo_travelers",), group_hints=set(), remaining_rank={NEXT: 0, OTHER: 1}, **common,
        )
        self.assertEqual(current, (0, 1, 999, 0, "photo_current"))
        self.assertLess(current, next_key)
        self.assertLess(current, other)

        family = _candidate_sort_key(
            card_id="photo_next", node_id=NEXT, current_node_id=None,
            target_groups=("family",), group_hints={"family"}, remaining_rank={}, **common,
        )
        non_family = _candidate_sort_key(
            card_id="photo_current", node_id=CURRENT, current_node_id=None,
            target_groups=("friends",), group_hints={"family"}, remaining_rank={}, **common,
        )
        self.assertEqual(family[:2], (2, 0))
        self.assertLess(family, non_family)

        route_first = _candidate_sort_key(
            card_id="photo_next", node_id=NEXT, current_node_id=None,
            target_groups=("family",), group_hints=set(), remaining_rank={NEXT: 0, OTHER: 1}, **common,
        )
        route_second = _candidate_sort_key(
            card_id="photo_other", node_id=OTHER, current_node_id=None,
            target_groups=("solo_travelers",), group_hints=set(), remaining_rank={NEXT: 0, OTHER: 1}, **common,
        )
        self.assertEqual(route_first[:3], (2, 1, 0))
        self.assertLess(route_first, route_second)

        themed = _candidate_sort_key(
            card_id="photo_b", node_id="same", current_node_id=None,
            target_groups=(), group_hints=set(), remaining_rank={}, themes={"craft_detail"}, requested_themes={"craft_detail"},
            is_current_child=False,
        )
        unthemed = _candidate_sort_key(
            card_id="photo_a", node_id="same", current_node_id=None,
            target_groups=(), group_hints=set(), remaining_rank={}, themes=set(), requested_themes={"craft_detail"},
            is_current_child=False,
        )
        self.assertLess(themed, unthemed)
        same_a = _candidate_sort_key(
            card_id="photo_a", node_id="same", current_node_id=None,
            target_groups=(), group_hints=set(), remaining_rank={}, themes=set(), requested_themes=set(),
            is_current_child=False,
        )
        same_b = _candidate_sort_key(
            card_id="photo_b", node_id="same", current_node_id=None,
            target_groups=(), group_hints=set(), remaining_rank={}, themes=set(), requested_themes=set(),
            is_current_child=False,
        )
        self.assertLess(same_a, same_b)

    def test_photo_intent_and_route_conflict_are_deterministic(self) -> None:
        self.assertTrue(is_explicit_photo_request("给我推荐几个打卡点"))
        self.assertTrue(is_explicit_photo_request("这里怎么拍？"))
        self.assertFalse(is_explicit_photo_request("灰塑是什么？"))
        self.assertTrue(has_photo_route_conflict("把这个打卡点加入路线"))

    def test_unsafe_photo_request_requires_action_and_protected_feature(self) -> None:
        for request in (
            "我想踩在栏杆上拍照，怎么拍？",
            "可以爬到栏杆上拍照吗？",
            "让孩子坐在栏杆上拍一张。",
            "能倚靠石狮拍照吗？",
            "翻过围挡拍会不会更好？",
        ):
            self.assertTrue(is_unsafe_photo_request(request), request)
        for request in ("栏杆怎么拍比较好？", "我想踩点拍照。", "让孩子坐在安全休息区拍照。"):
            self.assertFalse(is_unsafe_photo_request(request), request)

    def test_unsafe_photo_requests_refuse_before_candidate_lookup_and_keep_state_unchanged(self) -> None:
        tour = {"visited_stop_ids": [CURRENT], "remaining_stop_ids": [NEXT], "route_status": "touring"}
        profile = {"audience_mode": "family", "interaction_mode": "normal"}
        before_tour, before_profile = deepcopy(tour), deepcopy(profile)
        candidate_validator = Mock(side_effect=AssertionError("must not validate candidates"))
        query_selector = Mock(side_effect=AssertionError("must not query candidates"))

        for request in (
            "我想踩在栏杆上拍照，怎么拍？",
            "可以爬到栏杆上拍照吗？",
            "让孩子坐在栏杆上拍一张。",
            "能倚靠石狮拍照吗？",
            "翻过围挡拍会不会更好？",
        ):
            result = answer_photo_request(
                request,
                point_context={"node_id": CURRENT, "name": "月台"},
                tour_state=tour,
                visitor_profile=profile,
                candidate_validator=candidate_validator,
                query_selector=query_selector,
            )
            self.assertEqual(result["mode"], "photo_safety_refusal")
            self.assertEqual(result["photo_spots"], [])
            self.assertIn("不建议", result["message"])
            self.assertIn("平地", result["message"])

        candidate_validator.assert_not_called()
        query_selector.assert_not_called()
        self.assertEqual(tour, before_tour)
        self.assertEqual(profile, before_profile)

    def test_restricted_photo_methods_refuse_before_candidate_lookup(self) -> None:
        candidate_validator = Mock(side_effect=AssertionError("must not validate candidates"))
        query_selector = Mock(side_effect=AssertionError("must not query candidates"))

        cases = {
            "我想带无人机去拍陈家祠，可以直接飞吗？": "全域禁飞",
            "室内拍展柜可以开闪光灯吗？": "禁止使用闪光灯",
            "我可以来这里商拍吗？": "未经报备",
        }
        for request, expected in cases.items():
            with self.subTest(request=request):
                self.assertTrue(is_unsafe_photo_request(request))
                result = answer_photo_request(
                    request,
                    point_context=None,
                    tour_state=None,
                    visitor_profile=None,
                    candidate_validator=candidate_validator,
                    query_selector=query_selector,
                )
                self.assertEqual(result["mode"], "photo_safety_restriction")
                self.assertEqual(result["photo_spots"], [])
                self.assertIn(expected, result["message"])

        candidate_validator.assert_not_called()
        query_selector.assert_not_called()

    def test_safe_photo_requests_keep_existing_candidate_path(self) -> None:
        for request in ("栏杆怎么拍比较好？", "我想踩点拍照。", "让孩子坐在安全休息区拍照。"):
            result = answer_photo_request(
                request,
                point_context=None,
                tour_state=None,
                visitor_profile={},
                candidate_validator=_candidates,
                query_selector=_selector,
            )
            self.assertEqual(result["mode"], "photo_recommendation")

    def test_current_point_candidate_outranks_remaining_route(self) -> None:
        result = answer_photo_request(
            "这里怎么拍？", point_context={"node_id": CURRENT, "name": "月台"},
            tour_state={"remaining_stop_ids": [NEXT, OTHER]}, visitor_profile={},
            candidate_validator=_candidates, query_selector=_selector,
        )
        self.assertEqual(result["mode"], "photo_recommendation")
        self.assertEqual(result["photo_spots"][0]["node_id"], CURRENT)
        self.assertIn("项目编辑", result["message"])
        self.assertIn("现场为准", result["message"])
        self.assertNotIn("最佳", result["message"])
        self.assertNotIn("热门", result["message"])

    def test_whole_site_result_uses_route_then_stable_limit_of_three(self) -> None:
        # Root-level nodes may have no parent.  With no current location they
        # must not be misclassified through the accidental comparison
        # ``None == None`` as a current-area child.
        with patch("photo_spot_runtime._parent_node_ids", return_value={CURRENT: None, NEXT: "front", OTHER: None}):
            result = answer_photo_request(
                "推荐几个打卡点", point_context=None,
                tour_state={"remaining_stop_ids": [NEXT, OTHER]}, visitor_profile={},
                candidate_validator=_candidates, query_selector=_selector,
            )
        self.assertLessEqual(len(result["photo_spots"]), 3)
        self.assertEqual(result["photo_spots"][0]["node_id"], NEXT)
        self.assertEqual(len({item["node_id"] for item in result["photo_spots"]}), len(result["photo_spots"]))

    def test_family_and_solo_words_are_one_turn_ranking_hints(self) -> None:
        family = answer_photo_request("适合一家人拍照的地方有哪些？", point_context=None, tour_state=None, visitor_profile={}, candidate_validator=_candidates, query_selector=_selector)
        solo = answer_photo_request("有没有适合一个人拍的角度？", point_context=None, tour_state=None, visitor_profile={}, candidate_validator=_candidates, query_selector=_selector)
        self.assertEqual(family["photo_spots"][0]["node_id"], NEXT)
        self.assertEqual(solo["photo_spots"][0]["node_id"], OTHER)

    def test_deictic_request_without_position_clarifies(self) -> None:
        result = answer_photo_request("这里怎么拍？", point_context=None, tour_state=None, visitor_profile=None, candidate_validator=_candidates, query_selector=_selector)
        self.assertEqual(result["mode"], "photo_location_required")

    def test_current_point_without_candidate_is_disclosed_before_route_fallback(self) -> None:
        candidates = _candidates()
        candidates["photo_current"] = {**candidates["photo_current"], "available": False}
        result = answer_photo_request(
            "这里怎么拍？", point_context={"node_id": CURRENT, "name": "月台"},
            tour_state={"remaining_stop_ids": [NEXT]}, visitor_profile={},
            candidate_validator=lambda: candidates, query_selector=_selector,
        )
        self.assertEqual(result["mode"], "photo_recommendation")
        self.assertEqual(result["photo_spots"][0]["node_id"], NEXT)
        self.assertIn("当前点位暂没有", result["message"])

    def test_route_change_is_not_partially_executed(self) -> None:
        result = answer_photo_request("把这个打卡点加入路线", point_context={"node_id": CURRENT}, tour_state=None, visitor_profile=None, candidate_validator=_candidates, query_selector=_selector)
        self.assertEqual(result["mode"], "photo_clarification")
        self.assertEqual(result["photo_spots"], [])

    def test_no_candidates_falls_back_to_non_contact_safety_message(self) -> None:
        result = answer_photo_request("推荐打卡点", point_context=None, tour_state=None, visitor_profile=None, candidate_validator=lambda: {}, query_selector=_selector)
        self.assertEqual(result["mode"], "photo_unavailable")
        self.assertIn("不要触摸、倚靠、攀爬或跨越", result["message"])

    def test_photo_answer_never_mutates_tour_or_profile(self) -> None:
        tour = {"visited_stop_ids": [CURRENT], "remaining_stop_ids": [NEXT], "route_status": "touring"}
        profile = {"audience_mode": "family", "interaction_mode": "listen_only"}
        before_tour, before_profile = deepcopy(tour), deepcopy(profile)
        result = answer_photo_request("适合一家人拍的吗？", point_context=None, tour_state=tour, visitor_profile=profile, candidate_validator=_candidates, query_selector=_selector)
        self.assertEqual(tour, before_tour)
        self.assertEqual(profile, before_profile)
        self.assertNotIn("找一找", result["message"])


if __name__ == "__main__":
    unittest.main()
