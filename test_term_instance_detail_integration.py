"""P1-10 current-point craft instances with same-object detail evidence."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question
from tour_state import start_tour


def _entry(name: str, content: str, **identity: str) -> dict:
    return {
        "document": "08_ornament_items.md",
        "title_path": ["陈家祠建筑装饰条目知识库", name],
        "source_ids": ["S11"],
        "content": content,
        **identity,
    }


def _arrived(node_id: str) -> tuple[dict, dict]:
    tour = start_tour(plan_template("highlights_30"))
    interaction = initialize_interaction(tour)
    arrival = handle_tour_event(tour, interaction, "arrive_at_stop", node_id=node_id)
    return arrival["tour_state"], arrival["interaction_state"]


class TermInstanceDetailIntegrationTests(unittest.TestCase):
    def _answer(self, query: str, node_id: str, payload: list[dict]) -> tuple[dict, dict, dict, list[str]]:
        tour, interaction = _arrived(node_id)
        before_tour, before_interaction = deepcopy(tour), deepcopy(interaction)
        calls: list[str] = []

        def search(retrieval_query: str) -> str:
            calls.append(retrieval_query)
            return json.dumps({"evidence": payload}, ensure_ascii=False)

        result = answer_tour_question(query, tour, interaction, search)
        self.assertEqual(tour, before_tour)
        self.assertEqual(interaction, before_interaction)
        return result, tour, interaction, calls

    def test_front_center_uses_exact_status_object_evidence_after_craft_overview(self):
        result, _, _, calls = self._answer(
            "这里的石雕是什么？",
            "stop_front_courtyard_center",
            [_entry(
                "状元及第",
                "类型：石雕。此图雕高中状元者身穿官服，其身后一童子手举华盖。",
                ornament_id="orn_080",
                craft="石雕",
                node_id="stop_front_courtyard_center",
            )],
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual([item["ornament_id"] for item in result["term_instances"]], ["orn_080"])
        self.assertEqual(result["instance_details"][0]["ornament_id"], "orn_080")
        self.assertIn(result["instance_details"][0]["coverage_level"], {"partial", "full"})
        self.assertEqual(result["instance_details"][0]["source_ids"], ["S11"])
        self.assertTrue(result["instance_details"][0]["used_for_visitor_answer"])
        self.assertEqual(result["suggested_follow_up_ornament_ids"], ["orn_080"])
        self.assertTrue(any("orn_080" in query and "状元及第" in query for query in calls))
        self.assertIn("状元及第", result["message"])
        self.assertIn("身穿官服", result["message"])
        self.assertIn("首进正门南面", result["message"])
        self.assertNotIn("引福归堂", result["message"])
        self.assertTrue(any("S10" in entry.get("source_ids", []) for entry in result["evidence"]))
        self.assertTrue(any("S11" in entry.get("source_ids", []) for entry in result["evidence"]))

    def test_wrong_object_and_craft_evidence_cannot_enter_status_detail(self):
        result, _, _, _ = self._answer(
            "这里的石雕是什么？",
            "stop_front_courtyard_center",
            [
                _entry("引福归堂", "类型：石雕。此图雕钟馗一手执扇。"),
                _entry("踏雪寻梅", "类型：石雕。画面描绘孟浩然骑驴寻梅。"),
                {
                    "document": "07_ornament_crafts.md",
                    "title_path": ["陈家祠建筑装饰工艺总览", "石雕"],
                    "source_ids": ["S10"],
                    "content": "石雕工艺总述。",
                },
            ],
        )
        detail = result["instance_details"][0]
        self.assertEqual(detail["ornament_id"], "orn_080")
        self.assertEqual(detail["source_ids"], [])
        self.assertFalse(detail["used_for_visitor_answer"])
        self.assertIn("资料目前只足以确认", result["message"])
        self.assertNotIn("引福归堂", result["message"])
        self.assertNotIn("踏雪寻梅", result["message"])

    def test_front_north_rejects_same_name_wood_evidence(self):
        result, _, _, _ = self._answer(
            "前庭的石雕是什么？",
            "stop_front_courtyard_center",
            [
                _entry("踏雪寻梅", "类型：木雕。画面描绘木雕版本。", craft="木雕"),
                _entry(
                    "踏雪寻梅",
                    "类型：石雕。画面描绘孟浩然踏雪骑驴寻梅的诗意场景。",
                    ornament_id="orn_074",
                    craft="石雕",
                    node_id="stop_front_courtyard_north",
                ),
            ],
        )
        self.assertEqual(result["instance_context_origin"], "explicit_query_location")
        self.assertEqual([item["ornament_id"] for item in result["term_instances"]], ["orn_074"])
        self.assertEqual(result["instance_details"][0]["source_ids"], ["S11"])
        self.assertIn("孟浩然踏雪骑驴寻梅", result["message"])
        self.assertNotIn("木雕版本", result["message"])
        self.assertNotIn("- 类型：", result["message"])

    def test_moon_platform_keeps_only_its_exact_object_detail(self):
        result, _, _, _ = self._answer(
            "这里的石雕是什么？",
            "label_moon_platform",
            [
                _entry("状元及第", "类型：石雕。此图雕高中状元者身穿官服。"),
                _entry(
                    "引福归堂",
                    "类型：石雕。钟馗能镇宅避邪、祛恶纳福。此图雕钟馗一手执扇，一手引福归堂。",
                    ornament_id="orn_078",
                    craft="石雕",
                    node_id="label_moon_platform",
                ),
            ],
        )
        self.assertEqual([item["ornament_id"] for item in result["term_instances"]], ["orn_078"])
        self.assertEqual(result["instance_details"][0]["ornament_id"], "orn_078")
        self.assertIn("引福归堂", result["message"])
        self.assertIn("钟馗", result["message"])
        self.assertNotIn("状元及第", result["message"])

    def test_without_reliable_point_keeps_whole_site_names_without_object_detail_retrieval(self):
        calls: list[str] = []
        result = answer_tour_question(
            "石雕是什么？",
            None,
            None,
            lambda query: calls.append(query) or self.fail("whole-site examples must not fetch object packets"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["instance_context_origin"], "whole_site")
        self.assertLessEqual(len(result["term_instances"]), 2)
        self.assertEqual(result["instance_details"], [])
        self.assertEqual(calls, [])

    def test_combined_craft_answers_hide_internal_provenance_but_retain_audit_evidence(self):
        cases = (
            (
                "stop_front_courtyard_center",
                "这里的石雕是什么？",
                "状元及第",
                "orn_080",
                [_entry(
                    "状元及第",
                    "类型：石雕。画面刻有高中状元者身穿官服。",
                    ornament_id="orn_080",
                    craft="石雕",
                    node_id="stop_front_courtyard_center",
                )],
            ),
            (
                "stop_front_courtyard_north",
                "这里的石雕是什么？",
                "踏雪寻梅",
                "orn_074",
                [_entry(
                    "踏雪寻梅",
                    "类型：石雕。画面描绘孟浩然踏雪寻梅。",
                    ornament_id="orn_074",
                    craft="石雕",
                    node_id="stop_front_courtyard_north",
                )],
            ),
            (
                "label_moon_platform",
                "这里的石雕是什么？",
                "引福归堂",
                "orn_078",
                [_entry(
                    "引福归堂",
                    "类型：石雕。钟馗一手执扇，一手引福归堂。",
                    ornament_id="orn_078",
                    craft="石雕",
                    node_id="label_moon_platform",
                )],
            ),
        )
        for node_id, query, ornament_name, ornament_id, payload in cases:
            with self.subTest(node_id=node_id):
                result, _, _, _ = self._answer(query, node_id, payload)
                self.assertIn(ornament_name, result["message"])
                for forbidden in ("S10", "S11", "来源：", ".md", ornament_id, node_id):
                    self.assertNotIn(forbidden, result["message"])
                self.assertTrue(any("S10" in item.get("source_ids", []) for item in result["evidence"]))
                self.assertEqual(result["instance_details"][0]["source_ids"], ["S11"])

        whole_site = answer_tour_question(
            "石雕是什么？", None, None,
            lambda _: self.fail("whole-site craft overview must not retrieve object packets"),
        )
        self.assertEqual(whole_site["instance_context_origin"], "whole_site")
        for forbidden in ("S10", "S11", "来源：", ".md", "orn_", "node_id"):
            self.assertNotIn(forbidden, whole_site["message"])
        self.assertTrue(any("S10" in item.get("source_ids", []) for item in whole_site["evidence"]))


if __name__ == "__main__":
    unittest.main()
