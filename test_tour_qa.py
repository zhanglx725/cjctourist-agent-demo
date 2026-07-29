"""Offline unit tests for the A2 point-aware RAG orchestration layer."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question, build_tour_qa_query, load_guide_cards
from tour_state import start_tour


EVIDENCE = {
    "document": "08_ornament_items.md",
    "title_path": ["陈家祠建筑装饰条目知识库", "独角狮"],
    "source_ids": ["S11"],
    "content": "独角狮为陈家祠建筑装饰题材之一。",
}


class TourQaTests(unittest.TestCase):
    def setUp(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        self.tour = arrived["tour_state"]
        self.interaction = arrived["interaction_state"]

    @staticmethod
    def _success_search(query: str) -> str:
        return json.dumps({"query": query, "evidence": [EVIDENCE]}, ensure_ascii=False)

    def test_current_point_detail_question_uses_local_craft_instances_and_cites_evidence(self):
        calls = []
        def local_search(query):
            calls.append(query)
            if query.startswith("石雕 是什么"):
                return json.dumps({"evidence": [EVIDENCE]}, ensure_ascii=False)
            return json.dumps({"evidence": [EVIDENCE]}, ensure_ascii=False)
        result = answer_tour_question(
            "这里的石雕有什么特点？", self.tour, self.interaction, local_search
        )
        self.assertEqual(result["mode"], "current_point_craft_features")
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all("石雕" in query for query in calls))
        self.assertTrue(result["local_ornaments"])
        self.assertTrue(all(item["craft"] == "石雕" for item in result["local_ornaments"]))
        self.assertIn("08_ornament_items.md", result["message"])
        self.assertIn("S11", result["message"])
        self.assertEqual(result["presentation"]["phase"], "explaining")
        self.assertIn("explanation_finished", [item["id"] for item in result["presentation"]["actions"]])

    def test_current_point_inventory_is_deterministic_and_does_not_call_rag(self):
        result = answer_tour_question(
            "这里有什么？", self.tour, self.interaction, lambda _: self.fail("inventory must not call RAG")
        )
        self.assertEqual(result["mode"], "inventory")
        self.assertEqual(result["inventory"]["node_id"], "stop_front_courtyard_center")
        self.assertEqual(len(result["inventory"]["ornaments"]), 11)
        self.assertIn("独角狮", result["message"])
        self.assertIn("工艺分布", result["message"])

    def test_explicit_point_inventory_works_without_an_active_route(self):
        result = answer_tour_question(
            "月台有哪些装饰？", None, None, lambda _: self.fail("inventory must not call RAG")
        )
        self.assertEqual(result["mode"], "inventory")
        self.assertEqual(result["inventory"]["node_id"], "label_moon_platform")
        self.assertGreater(result["inventory"]["craft_distribution"].get("石雕", 0), 0)

    def test_explicit_point_overview_is_hard_bounded_to_its_card(self):
        rear_tour = deepcopy(self.tour)
        rear_tour["current_stop_id"] = "stop_rear_west_courtyard"
        before = deepcopy(rear_tour)
        result = answer_tour_question(
            "讲讲月台。", rear_tour, self.interaction,
            lambda _: self.fail("explicit point overview must use its reviewed card"),
        )
        self.assertEqual(result["mode"], "inventory")
        self.assertEqual(result["inventory"]["node_id"], "label_moon_platform")
        self.assertEqual(result["point_context"]["node_id"], "label_moon_platform")
        self.assertEqual(rear_tour, before)

    def test_general_fact_question_is_not_restricted_to_current_point(self):
        result = answer_tour_question(
            "陈家祠什么时候建成？", self.tour, self.interaction, self._success_search
        )
        self.assertEqual(result["retrieval_query"], "陈家祠什么时候建成？")
        self.assertEqual(result["evidence"], [EVIDENCE])

    def test_same_deictic_craft_question_changes_local_examples_by_current_node(self):
        moon_tour = start_tour(plan_template("highlights_30"))
        moon_interaction = initialize_interaction(moon_tour)
        moon = handle_tour_event(moon_tour, moon_interaction, "arrive_at_stop", node_id="label_moon_platform")
        first = answer_tour_question("这里的灰塑有什么特点？", self.tour, self.interaction, self._success_search)
        second = answer_tour_question("这里的灰塑有什么特点？", moon["tour_state"], moon["interaction_state"], self._success_search)
        self.assertNotEqual(
            {item["ornament_id"] for item in first["local_ornaments"]},
            {item["ornament_id"] for item in second["local_ornaments"]},
        )
        cards = load_guide_cards()
        for result in (first, second):
            allowed = {item["ornament_id"] for item in cards[result["point_context"]["node_id"]]["ornaments"]}
            self.assertTrue({item["ornament_id"] for item in result["local_ornaments"]}.issubset(allowed))

    def test_current_point_without_craft_does_not_use_global_instances(self):
        base = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(base)
        self_arrival = handle_tour_event(base, interaction, "arrive_at_stop", node_id="stop_rear_courtyard_west")
        result = answer_tour_question(
            "这里的灰塑有什么特点？", self_arrival["tour_state"], self_arrival["interaction_state"],
            lambda _: self.fail("no local craft must not call RAG"),
        )
        self.assertEqual(result["mode"], "current_craft_absent")
        self.assertIn("没有灰塑", result["message"])

    def test_deictic_craft_definition_requires_a_local_reviewed_association(self):
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        result = answer_tour_question(
            "这里的灰塑是什么意思？", self.tour, self.interaction,
            lambda _: self.fail("eligible term card should not need RAG"),
        )
        self.assertEqual(result["mode"], "current_point_term_card")
        self.assertEqual(result["point_context"]["node_id"], "stop_front_courtyard_center")
        self.assertIn("确有灰塑对象", result["message"])
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

        absent = deepcopy(self.tour)
        absent["current_stop_id"] = "stop_rear_courtyard_west"
        result = answer_tour_question(
            "这里的灰塑是什么意思？", absent, self.interaction,
            lambda _: self.fail("absent local craft must not call RAG"),
        )
        self.assertEqual(result["mode"], "current_craft_absent")
        self.assertIn("没有灰塑", result["message"])

    def test_museum_wide_craft_question_keeps_base_rag_behavior(self):
        result = answer_tour_question("陈家祠灰塑有什么特点？", self.tour, self.interaction, self._success_search)
        self.assertEqual(result["mode"], "rag")
        self.assertEqual(result["retrieval_query"], "陈家祠灰塑有什么特点？")
        self.assertEqual(result["evidence"], [EVIDENCE])

    def test_question_never_mutates_tour_or_interaction_state(self):
        before_tour = deepcopy(self.tour)
        before_interaction = deepcopy(self.interaction)
        answer_tour_question("这里有什么？", self.tour, self.interaction, self._success_search)
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_self_arrival_uses_real_current_position_without_route_progress(self):
        base_tour = start_tour(plan_template("highlights_30"))
        base_interaction = initialize_interaction(base_tour)
        self_arrival = handle_tour_event(
            base_tour, base_interaction, "arrive_at_stop", node_id="label_first_main_hall"
        )
        result = answer_tour_question(
            "这里有什么？", self_arrival["tour_state"], self_arrival["interaction_state"], self._success_search
        )
        self.assertEqual(result["point_context"]["node_id"], "label_first_main_hall")
        self.assertEqual(self_arrival["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(self_arrival["interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")

    def test_no_active_tour_uses_reviewed_craft_overview_without_presentation(self):
        craft_payload = json.dumps(
            {
                "evidence": [
                    {
                        "document": "07_ornament_crafts.md",
                        "title_path": ["陈家祠建筑装饰工艺总览", "灰塑：岭南建筑的现场堆塑艺术"],
                        "source_ids": ["S10"],
                        "content": (
                            "- **工艺性质与位置**：灰塑是珠江三角洲传统建筑中广泛使用的装饰艺术。 "
                            "- **材料与流程**：艺人以石灰为主料，加入发酵后的稻草或草纸，"
                            "制成草筋灰或纸筋灰；通常先用草筋灰堆塑造型，再用纸筋灰细塑表面。"
                        ),
                    }
                ]
            },
            ensure_ascii=False,
        )
        result = answer_tour_question("灰塑是什么？", None, None, lambda _: craft_payload)
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["retrieval_query"], "灰塑 工艺性质与位置")
        self.assertIn("珠江三角洲传统建筑", result["message"])
        self.assertNotIn("草筋灰或纸筋灰", result["message"])
        self.assertIsNone(result["presentation"])

    def test_unknown_point_and_missing_point_card_fail_safely(self):
        unknown = answer_tour_question(
            "不存在展厅有哪些装饰？", self.tour, self.interaction, lambda _: self.fail("unknown point must not call RAG")
        )
        self.assertEqual(unknown["mode"], "inventory_error")
        self.assertIn("未找到", unknown["message"])
        missing = answer_tour_question(
            "首进正厅有哪些装饰？", self.tour, self.interaction, lambda _: self.fail("missing card must not call RAG")
        )
        self.assertEqual(missing["mode"], "inventory_missing_card")
        self.assertIn("讲解包缺失", missing["message"])

    def test_no_evidence_and_retrieval_exception_are_safe(self):
        before_tour = deepcopy(self.tour)
        before_interaction = deepcopy(self.interaction)
        no_evidence = answer_tour_question(
            "这里的石雕有什么特点？", self.tour, self.interaction, lambda _: json.dumps({"evidence": []})
        )
        self.assertIn("资料不足", no_evidence["message"])
        self.assertEqual(no_evidence["evidence"], [])
        self.assertEqual(no_evidence["presentation"]["phase"], "explaining")

        unavailable = answer_tour_question(
            "这里的石雕有什么特点？", self.tour, self.interaction, lambda _: (_ for _ in ()).throw(RuntimeError("offline"))
        )
        self.assertIn("暂时不可用", unavailable["message"])
        self.assertEqual(unavailable["evidence"], [])
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_research_without_exact_card_falls_back_to_visible_base_evidence(self):
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        with patch("tour_qa.retrieve_research_cards", return_value={"status": "no_eligible_match", "cards": []}):
            result = answer_tour_question(
                "从研究角度讲讲陈家祠的空间布局。",
                self.tour, self.interaction, self._success_search,
            )
        self.assertEqual(result["mode"], "research_rag_fallback")
        self.assertIn("基础资料回答", result["message"])
        self.assertIn("S11", result["message"])
        self.assertEqual(result["research_cards"], [])
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_inexact_comparison_card_falls_back_to_separate_base_rag_queries(self):
        calls = []

        def search(query: str) -> str:
            calls.append(query)
            return self._success_search(query)

        with patch("tour_qa.retrieve_gated_comparison", return_value={"status": "no_matching_card", "card": None}):
            result = answer_tour_question(
                "灰塑和木雕有什么区别？", self.tour, self.interaction, search,
            )
        self.assertEqual(result["mode"], "comparison_rag_fallback")
        self.assertEqual(result["comparison"], None)
        self.assertEqual(result["comparison_subjects"], ("灰塑", "木雕"))
        self.assertEqual(calls, ["灰塑 是什么 工艺 特点", "木雕 是什么 工艺 特点"])
        self.assertIn("S11", result["message"])


if __name__ == "__main__":
    unittest.main()
