"""P1-09 regression tests for reviewed object-detail narration."""

from __future__ import annotations

import json
import unittest

from controlled_knowledge_query import ControlledKnowledgePlan
from ornament_clarification import create_pending_ornament_clarification
from ornament_detail_runtime import build_object_evidence_view, render_object_detail
from tour_qa import answer_tour_question, load_guide_cards


def _entry(title: str, content: str, source: str = "S11") -> dict:
    return {
        "document": "08_ornament_items.md",
        "title_path": ["陈家祠建筑装饰条目知识库", title],
        "source_ids": [source],
        "content": content,
    }


JIANG_CONTENT = (
    "类型：木雕。故事取材于《三国演义》。孙权用计骗取孙夫人携刘备的儿子阿斗回东吴探母，"
    "企图把阿斗作为人质威逼刘备交还荆州。画面为张飞闻讯后，赤膊上阵，"
    "手持丈八蛇矛在江中拦截东吴船只夺阿斗的情景。"
)

CHIBI_CONTENT = (
    "故事取材于《三国演义》。刮东风之夜，周瑜部下黄盖假装降曹，"
    "带着装满柴草的战船驶向曹军，点着战船。雕饰上方可见“周”字大旗，"
    "中部描绘曹军士兵在“曹”字大旗下乘船逃窜的情景。"
)


class OrnamentDetailRuntimeTests(unittest.TestCase):
    def test_confirmed_primary_matrix_uses_only_current_reviewed_mappings(self):
        expected = {
            "stop_front_courtyard_center": {
                "orn_005": ("独角狮", "灰塑"),
                "orn_008": ("福禄寿", "灰塑"),
                "orn_072": ("石狮子", "石雕"),
            },
            "label_moon_platform": {
                "orn_041": ("截江夺阿斗", "木雕"),
                "orn_078": ("引福归堂", "石雕"),
                "orn_089": ("书字换鹅", "陶塑"),
            },
            "stop_rear_west_courtyard": {
                "orn_034": ("赤壁之战", "木雕"),
                "orn_049": ("三顾茅庐", "木雕"),
                "orn_003": ("宝相花", "灰塑"),
            },
        }
        cards = load_guide_cards()
        for node_id, objects in expected.items():
            with self.subTest(node_id=node_id):
                actual = {
                    item["ornament_id"]: (item["name"], item["craft"])
                    for item in cards[node_id]["ornaments"]
                }
                for ornament_id, identity in objects.items():
                    self.assertEqual(actual.get(ornament_id), identity)

        front = cards["stop_front_courtyard_north"]["ornaments"]
        taxue = [item for item in front if item["name"] == "踏雪寻梅"]
        self.assertEqual(
            [(item["ornament_id"], item["craft"]) for item in taxue],
            [("orn_051", "木雕"), ("orn_074", "石雕")],
        )
        self.assertNotIn("orn_052", {item["ornament_id"] for item in front})
        abnormal = next(item for item in cards["stop_front_courtyard_center"]["ornaments"] if item["ornament_id"] == "orn_083")
        self.assertEqual(abnormal["craft"], "凤穿牡丹）（陶塑")

    def test_point_and_named_ornament_answer_uses_only_the_named_object_evidence(self):
        calls: list[str] = []

        def search(query: str) -> str:
            calls.append(query)
            return json.dumps({"evidence": [_entry("截江夺阿斗", JIANG_CONTENT)]}, ensure_ascii=False)

        result = answer_tour_question("给我讲讲月台上的截江夺阿斗。", None, None, search)

        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_041")
        self.assertEqual(result["ornament_detail"]["node_id"], "label_moon_platform")
        self.assertEqual(result["ornament_detail"]["coverage_level"], "full")
        self.assertIn("张飞闻讯后", result["message"])
        self.assertNotIn("引福归堂", result["message"])
        self.assertNotIn("关联文物：", result["message"])
        self.assertNotIn("S11", result["message"])
        self.assertNotIn("08_ornament_items.md", result["message"])
        self.assertTrue(calls)

    def test_named_object_at_wrong_reviewed_point_fails_closed_without_retrieval(self):
        result = answer_tour_question(
            "给我讲讲后西庭的截江夺阿斗。", None, None,
            lambda _: self.fail("mismatched point and object must not retrieve"),
        )
        self.assertEqual(result["mode"], "ornament_detail_clarification")
        self.assertIn("未在", result["message"])
        self.assertIn("不会把其他点位的对象当作这里的内容", result["message"])
        self.assertEqual(result["evidence"], [])

    def test_same_name_without_point_is_ambiguous_instead_of_guessing(self):
        result = answer_tour_question(
            "给我讲讲踏雪寻梅。", None, None,
            lambda _: self.fail("candidate clarification must not retrieve"),
        )
        self.assertEqual(result["mode"], "ornament_candidate_clarification")
        self.assertIn("木雕《踏雪寻梅》", result["message"])
        self.assertIn("石雕《踏雪寻梅》", result["message"])

    def test_known_abnormal_craft_fails_closed_without_retrieval_or_internal_data(self):
        result = answer_tour_question(
            "给我讲讲前院中部的凤凰牡丹。", None, None,
            lambda _: self.fail("abnormal craft must fail closed before retrieval"),
        )
        self.assertEqual(result["mode"], "ornament_detail_unavailable")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_083")
        self.assertEqual(result["ornament_detail"]["coverage_level"], "insufficient")
        self.assertNotIn("凤穿牡丹）（陶塑", result["message"])
        self.assertNotIn("orn_083", result["message"])

    def test_inventory_question_stays_inventory_even_when_the_point_has_objects(self):
        result = answer_tour_question(
            "月台有什么？", None, None,
            lambda _: self.fail("reviewed inventory must not retrieve"),
        )
        self.assertEqual(result["mode"], "inventory")
        self.assertIn("现有点位清单", result["message"])

    def test_detail_answer_does_not_mutate_route_or_profile_inputs(self):
        tour_state = {
            "current_stop_id": "label_moon_platform",
            "visited_stop_ids": ["stop_front_courtyard_center"],
            "pending_stop_id": "label_moon_platform",
        }
        profile = {"interaction_mode": "listen_only"}
        before_state = json.loads(json.dumps(tour_state))
        before_profile = json.loads(json.dumps(profile))
        result = answer_tour_question(
            "给我讲讲截江夺阿斗。", tour_state, None,
            lambda _: json.dumps({"evidence": [_entry("截江夺阿斗", JIANG_CONTENT)]}, ensure_ascii=False),
            visitor_profile=profile,
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(tour_state, before_state)
        self.assertEqual(profile, before_profile)
        self.assertNotIn("？", result["message"])

    def test_object_evidence_view_does_not_turn_craft_only_text_into_a_story(self):
        view = build_object_evidence_view(
            ornament_id="orn_005",
            name="独角狮",
            craft="灰塑",
            node_id="stop_front_courtyard_center",
            raw_location="建筑山墙垂脊前沿",
            evidence=[{
                "document": "07_ornament_crafts.md",
                "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"],
                "source_ids": ["S10"],
                "content": "灰塑以石灰为主料，常见于山墙和屋脊。",
            }],
        )
        self.assertEqual(view.coverage_level, "basic")
        self.assertEqual(view.story_sentences, ())
        rendered = render_object_detail(view, first=True, detailed=True)
        self.assertNotIn("传说", rendered.visitor_text)
        self.assertNotIn("辟邪", rendered.visitor_text)
        self.assertNotIn("S10", rendered.visitor_text)
        self.assertNotIn("审核", rendered.visitor_text)

    def test_craft_only_request_clarifies_without_object_retrieval(self):
        result = answer_tour_question(
            "只根据灰塑工艺，讲讲独角狮的完整传说和人物情节。",
            None,
            None,
            lambda _: self.fail("craft-only scope must not retrieve object evidence"),
        )
        self.assertEqual(result["mode"], "ornament_story_source_clarification")
        self.assertEqual(result["answer_mode"], "ornament_story_source_clarification")
        self.assertEqual(result["ornament_story_scope"]["requested_subject"], "独角狮")
        self.assertEqual(result["ornament_story_scope"]["required_scope"], "exact_ornament")
        self.assertEqual(result["evidence"], [])
        self.assertIn("无法证明", result["message"])
        self.assertNotIn("传说中的", result["message"])

    def test_exact_object_story_uses_only_matching_08_evidence(self):
        correct = _entry(
            "独角狮",
            "独角狮为灰塑装饰。传说中它守护门户。画面突出独角与狮身，寓意辟邪。",
        )
        wrong = _entry("福禄寿", "福禄寿表现吉祥题材，不属于独角狮故事。")
        result = answer_tour_question(
            "讲讲独角狮的完整传说和人物情节。",
            None,
            None,
            lambda _: json.dumps({"evidence": [wrong, correct]}, ensure_ascii=False),
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_005")
        self.assertEqual(result["ornament_detail"]["source_ids"], ["S11"])
        self.assertIn("守护门户", result["message"])
        self.assertNotIn("福禄寿", result["message"])
        self.assertEqual(len(result["ornament_detail"]["accepted_evidence"]), 1)
        self.assertEqual(len(result["ornament_detail"]["rejected_evidence"]), 1)

    def test_exact_object_story_beats_an_injected_broad_plan(self):
        plan = ControlledKnowledgePlan(
            domain="ornament_item",
            question_type="story",
            subject_text="独角狮",
            detail_level="brief",
        )
        result = answer_tour_question(
            "讲讲独角狮的完整传说和人物情节。",
            None,
            None,
            lambda _: json.dumps({"evidence": [_entry("独角狮", "独角狮是灰塑装饰。故事讲述它守护门户。 ")]}, ensure_ascii=False),
            normalized_knowledge_plan=plan,
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertNotIn("knowledge_plan", result)

    def test_same_name_candidates_use_one_canonical_wood_and_one_stone(self):
        first = answer_tour_question(
            "讲讲踏雪寻梅的故事。", None, None,
            lambda _: self.fail("candidate clarification must not retrieve stories"),
        )
        self.assertEqual(first["mode"], "ornament_candidate_clarification")
        candidates = first["ornament_candidates"]
        wood = next(candidate for candidate in candidates if candidate["craft"] == "木雕")
        stone = next(candidate for candidate in candidates if candidate["craft"] == "石雕")
        self.assertEqual(wood["candidate_kind"], "exact_object")
        self.assertEqual(wood["ornament_id"], "orn_051")
        self.assertTrue(wood["selectable_for_exact_detail"])
        self.assertEqual(stone["candidate_kind"], "exact_object")
        self.assertEqual(stone["ornament_id"], "orn_074")
        self.assertTrue(stone["selectable_for_exact_detail"])
        self.assertNotIn("orn_051", first["message"])
        self.assertNotIn("S11", first["message"])

    def test_same_name_stone_choice_uses_only_the_selected_exact_object(self):
        first = answer_tour_question("讲讲踏雪寻梅的故事。", None, None, lambda _: "{}")
        stone = _entry(
            "踏雪寻梅",
            "踏雪寻梅是一件石雕装饰。画面还原孟浩然踏雪骑驴寻梅的诗意场景。",
        )
        wood = _entry("踏雪寻梅", "踏雪寻梅是一件木雕装饰。故事源自孟浩然。")
        result = answer_tour_question(
            "石雕那个", None, None,
            lambda _: json.dumps({"evidence": [wood, stone]}, ensure_ascii=False),
            pending_ornament_clarification=first["pending_ornament_clarification"],
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_074")
        self.assertIn("骑驴寻梅", result["message"])
        self.assertNotIn("木雕装饰", result["message"])
        self.assertEqual(result["pending_ornament_clarification"], None)

    def test_same_name_wood_choice_locks_the_canonical_object(self):
        first = answer_tour_question("讲讲踏雪寻梅的故事。", None, None, lambda _: "{}")
        wood = _entry("踏雪寻梅", "踏雪寻梅是一件木雕装饰。故事源自孟浩然踏雪寻梅。")
        result = answer_tour_question(
            "木雕那个", None, None,
            lambda _: json.dumps({"evidence": [wood]}, ensure_ascii=False),
            pending_ornament_clarification=first["pending_ornament_clarification"],
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_051")
        self.assertIn("孟浩然", result["message"])
        self.assertNotIn("orn_051", result["message"])
        self.assertNotIn("orn_052", result["message"])

    def test_explicit_canonical_wood_request_bypasses_candidate_prompt(self):
        result = answer_tour_question(
            "讲讲木雕《踏雪寻梅》。", None, None,
            lambda _: json.dumps({"evidence": [
                _entry("踏雪寻梅", "踏雪寻梅是一件木雕装饰。故事源自孟浩然踏雪寻梅。")
            ]}, ensure_ascii=False),
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_051")
        self.assertNotIn("ornament_candidates", result)

    def test_old_pending_alias_group_revalidates_to_the_current_canonical_object(self):
        old_pending = create_pending_ornament_clarification(
            original_query="讲讲踏雪寻梅的故事。",
            subject_name="踏雪寻梅",
            requested_detail="story",
            evidence_scope="exact_ornament",
            candidates=[
                {
                    "choice_index": 1, "candidate_kind": "ambiguous_group",
                    "display_name": "踏雪寻梅", "craft": "木雕",
                    "node_id": "stop_front_courtyard_north", "node_name": "前庭",
                    "member_ornament_ids": ["orn_051", "orn_052"],
                    "selectable_for_exact_detail": False,
                },
                {
                    "choice_index": 2, "candidate_kind": "exact_object",
                    "display_name": "踏雪寻梅", "craft": "石雕",
                    "node_id": "stop_front_courtyard_north", "node_name": "前庭",
                    "ornament_id": "orn_074", "selectable_for_exact_detail": True,
                },
            ],
        )
        result = answer_tour_question(
            "木雕", None, None,
            lambda _: json.dumps({"evidence": [_entry("踏雪寻梅", "踏雪寻梅是一件木雕装饰。故事源自孟浩然。 ")]}, ensure_ascii=False),
            pending_ornament_clarification=old_pending,
        )
        self.assertEqual(result["mode"], "ornament_detail")
        self.assertEqual(result["ornament_detail"]["ornament_id"], "orn_051")
        self.assertIsNone(result["pending_ornament_clarification"])

    def test_craft_only_can_narrow_a_category_but_never_uses_wood_story_evidence(self):
        result = answer_tour_question(
            "只根据木雕工艺，讲讲踏雪寻梅的完整故事。", None, None,
            lambda _: self.fail("craft-only category must not retrieve evidence"),
        )
        self.assertEqual(result["mode"], "ornament_story_source_clarification")
        self.assertNotIn("ornament_candidate_audit", result)
        self.assertIn("无法证明", result["message"])

    def test_full_story_is_rendered_as_flat_paragraphs_without_internal_fields(self):
        view = build_object_evidence_view(
            ornament_id="orn_034",
            name="赤壁之战",
            craft="木雕",
            node_id="stop_rear_west_courtyard",
            raw_location="中进聚贤堂屏风",
            evidence=[_entry("赤壁之战", CHIBI_CONTENT)],
        )
        rendered = render_object_detail(view, first=True, detailed=False)
        self.assertEqual(view.coverage_level, "full")
        self.assertIn("黄盖假装降曹", rendered.visitor_text)
        self.assertNotIn("- ", rendered.visitor_text)
        self.assertNotIn("来源：S", rendered.visitor_text)
        self.assertNotIn("08_ornament_items.md", rendered.visitor_text)
        self.assertEqual(rendered.source_ids, ("S11",))


if __name__ == "__main__":
    unittest.main()
