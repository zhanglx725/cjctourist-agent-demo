"""P1-09 regression tests for reviewed object-detail narration."""

from __future__ import annotations

import json
import unittest

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
        self.assertGreaterEqual(
            sum(item["name"] == "踏雪寻梅" for item in front), 2,
            "同名对象必须保留为需要消歧的审核数据，而不能按名称猜测唯一对象。",
        )
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
        self.assertIn("不把其他点位对象当作本点内容", result["message"])
        self.assertEqual(result["evidence"], [])

    def test_same_name_without_point_is_ambiguous_instead_of_guessing(self):
        result = answer_tour_question(
            "给我讲讲踏雪寻梅。", None, None,
            lambda _: self.fail("ambiguous object must not retrieve"),
        )
        self.assertEqual(result["mode"], "ornament_detail_clarification")
        self.assertIn("多个已审核对象", result["message"])

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
        self.assertIn("已审核点位清单", result["message"])

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
