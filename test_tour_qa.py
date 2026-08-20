"""Offline unit tests for the A2 point-aware RAG orchestration layer."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from route_planner import plan_template
from controlled_knowledge_query import ControlledKnowledgePlan, is_public_visitor_message
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question, build_tour_qa_query, load_guide_cards
from tour_state import start_tour


EVIDENCE = {
    "document": "08_ornament_items.md",
    "title_path": ["陈家祠建筑装饰条目知识库", "独角狮"],
    "source_ids": ["S11"],
    "content": "独角狮为陈家祠建筑装饰题材之一。",
}
HISTORY_EVIDENCE = {
    "document": "02_history_architecture.md",
    "title_path": ["历史、建筑与文化特色", "历史沿革"],
    "source_ids": ["S02", "S04"],
    "content": (
        "1888 年，陈氏书院建祠公所成立并开始筹建。"
        "馆方历史页面写“1893 年落成”；"
        "广州市文化广电旅游局页面写“1888 年筹建、1894 年建成”。"
    ),
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

    def test_whole_venue_photo_question_uses_photo_check_in_candidates(self):
        result = answer_tour_question(
            "馆里哪里拍照好看？",
            self.tour,
            self.interaction,
            lambda _query: self.fail("photo discovery must not use RAG"),
        )
        self.assertEqual(result["mode"], "photo_recommendation")
        self.assertIn("拍照/打卡", result["message"])
        self.assertTrue(result["photo_spots"])
        self.assertTrue(is_public_visitor_message(result["message"]))

    @staticmethod
    def _success_search(query: str) -> str:
        return json.dumps({"query": query, "evidence": [EVIDENCE]}, ensure_ascii=False)

    def test_current_point_detail_question_uses_local_craft_instances_without_public_source_leak(self):
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
        self.assertNotIn("08_ornament_items.md", result["message"])
        self.assertNotIn("S11", result["message"])
        self.assertTrue(any("S11" in item.get("source_ids", []) for item in result["evidence"]))
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

    def test_single_date_fact_is_rendered_before_raw_rag_excerpt(self):
        def search(query: str) -> str:
            return json.dumps(
                {"query": query, "evidence": [HISTORY_EVIDENCE]},
                ensure_ascii=False,
            )

        result = answer_tour_question(
            "陈家祠什么时候建成？", self.tour, self.interaction, search
        )
        self.assertEqual(result["mode"], "single_fact")
        self.assertIn("1888 年开始筹建", result["message"])
        self.assertIn("1893 年落成", result["message"])
        self.assertIn("1894 年建成", result["message"])
        self.assertNotIn("02_history_architecture.md", result["message"])
        self.assertNotIn("根据本地知识库检索到的资料", result["message"])
        self.assertEqual(
            result["presentation"]["code"], "tour_qa_single_fact_answer"
        )

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

    def test_deictic_core_craft_definition_enhances_the_canonical_overview(self):
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        result = answer_tour_question(
            "这里的灰塑是什么意思？", self.tour, self.interaction,
            lambda _: self.fail("eligible term card should not need RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term_instances"][0]["node_id"], "stop_front_courtyard_center")
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_nonlocal_term_definition_uses_reviewed_examples_without_claiming_current_visibility(self):
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        result = answer_tour_question(
            "石雕是什么？", self.tour, self.interaction,
            lambda _: self.fail("eligible term answer should not need RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term"]["card_id"], "term_stone_carving")
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_080")
        self.assertIn("相关实例", result["message"])
        self.assertIn("现场可见情况请以实际为准", result["message"])
        self.assertNotIn("一定能看到", result["message"])
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_exact_term_beats_an_injected_broad_knowledge_plan(self):
        plan = ControlledKnowledgePlan(
            domain="ornament_craft",
            question_type="definition",
            subject_text="石雕",
            detail_level="brief",
        )
        result = answer_tour_question(
            "石雕是什么？",
            self.tour,
            self.interaction,
            lambda _: self.fail("term card must run before controlled retrieval"),
            normalized_knowledge_plan=plan,
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term"]["card_id"], "term_stone_carving")
        self.assertNotIn("knowledge_plan", result)

    def test_moon_platform_craft_overview_enhances_with_its_reviewed_instance(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="label_moon_platform"
        )
        before_tour = deepcopy(arrived["tour_state"])
        result = answer_tour_question(
            "石雕是什么？",
            arrived["tour_state"],
            arrived["interaction_state"],
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term"]["card_id"], "term_stone_carving")
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_078")
        self.assertEqual(result["term_instances"][0]["ornament_name"], "引福归堂")
        self.assertEqual(result["term_instances"][0]["node_id"], "label_moon_platform")
        self.assertEqual(result["instance_context_origin"], "physical_location")
        self.assertIn("月台的“引福归堂”", result["message"])
        self.assertEqual(arrived["tour_state"], before_tour)

    def test_front_north_craft_overview_keeps_only_its_reviewed_stone_instance(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_north"
        )
        before_tour = deepcopy(arrived["tour_state"])
        result = answer_tour_question(
            "这里的石雕是什么？",
            arrived["tour_state"],
            arrived["interaction_state"],
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["instance_context_origin"], "physical_location")
        self.assertEqual(
            [(item["node_id"], item["ornament_id"], item["ornament_name"])
            for item in result["term_instances"]],
            [("stop_front_courtyard_north", "orn_074", "踏雪寻梅")],
        )
        self.assertIn("前庭", result["message"])
        self.assertIn("踏雪寻梅", result["message"])
        self.assertNotIn("状元及第", result["message"])
        self.assertNotIn("引福归堂", result["message"])
        self.assertEqual(arrived["tour_state"], before_tour)

    def test_current_point_without_matching_craft_does_not_borrow_whole_site_instances(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="stop_rear_courtyard"
        )
        before_tour = deepcopy(arrived["tour_state"])
        result = answer_tour_question(
            "这里的石雕是什么？",
            arrived["tour_state"],
            arrived["interaction_state"],
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["instance_context_origin"], "physical_location")
        self.assertEqual(result["term_instances"], [])
        self.assertIn("暂未找到该工艺实例", result["message"])
        self.assertEqual(arrived["tour_state"], before_tour)

    def test_explicit_remote_point_only_changes_craft_instance_ranking(self):
        before_tour = deepcopy(self.tour)
        result = answer_tour_question(
            "月台的石雕是什么？",
            self.tour,
            self.interaction,
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_078")
        self.assertEqual(result["instance_context_origin"], "explicit_query_location")
        self.assertIn("月台的“引福归堂”", result["message"])
        self.assertIn("所问点位的相关实例", result["message"])
        self.assertNotIn("当前点的相关实例", result["message"])
        self.assertEqual(self.tour, before_tour)

    def test_deictic_core_craft_definition_uses_the_physical_point_for_instances(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="label_moon_platform"
        )
        before_tour = deepcopy(arrived["tour_state"])
        result = answer_tour_question(
            "我在这里，石雕是什么？",
            arrived["tour_state"],
            arrived["interaction_state"],
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_078")
        self.assertEqual(result["instance_context_origin"], "physical_location")
        self.assertEqual(arrived["tour_state"], before_tour)

    def test_explicit_research_question_is_not_hijacked_by_term_examples(self):
        result = answer_tour_question(
            "从学术研究角度，灰塑是什么？", self.tour, self.interaction,
            self._success_search,
        )
        self.assertNotIn(result["mode"], {"term_card", "current_point_term_card"})

        absent = deepcopy(self.tour)
        absent["current_stop_id"] = "stop_rear_courtyard_west"
        result = answer_tour_question(
            "这里的灰塑是什么意思？", absent, self.interaction,
            lambda _: self.fail("canonical craft overview must not call RAG"),
        )
        # Core-craft definitions keep their P1-05 overview.  This point has
        # no reviewed gray-plaster instance, so any optional example remains
        # explicitly framed as a whole-site audited association, not as an
        # object in front of the visitor.
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertEqual(result["instance_context_origin"], "physical_location")
        self.assertNotIn("眼前", result["message"])

    def test_museum_wide_craft_question_uses_canonical_craft_section(self):
        result = answer_tour_question(
            "陈家祠灰塑有什么特点？",
            self.tour,
            self.interaction,
            lambda _: self.fail("generic craft questions must not call vector RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertIsNone(result["retrieval_query"])
        self.assertEqual(
            [item["document"] for item in result["evidence"]],
            ["07_ornament_crafts.md"],
        )

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

    def test_no_active_tour_uses_reviewed_term_examples_without_presentation(self):
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
        result = answer_tour_question(
            "灰塑是什么？",
            None,
            None,
            lambda _: self.fail("generic craft questions must not call vector RAG"),
        )
        self.assertEqual(result["mode"], "whole_site_craft_overview")
        self.assertIsNone(result["retrieval_query"])
        self.assertEqual(result["term"]["card_id"], "term_lime_plaster_relief")
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_026")
        self.assertIn("杏林春燕", result["message"])
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
        self.assertIn("缺少这个点位的讲解资料", missing["message"])

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

    def test_research_without_exact_card_falls_back_without_internal_evidence_leak(self):
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        with patch("tour_qa.retrieve_research_cards", return_value={"status": "no_eligible_match", "cards": []}):
            result = answer_tour_question(
                "从研究角度讲讲陈家祠的空间布局。",
                self.tour, self.interaction, self._success_search,
            )
        self.assertEqual(result["mode"], "research_rag_fallback")
        self.assertIn("基础资料回答", result["message"])
        self.assertNotIn("S11", result["message"])
        self.assertNotIn(".md", result["message"])
        self.assertTrue(result["evidence"])
        self.assertTrue(any("S11" in item.get("source_ids", []) for item in result["evidence"]))
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
        self.assertNotIn("S11", result["message"])
        self.assertNotIn("08_ornament_items.md", result["message"])
        self.assertTrue(any("S11" in item.get("source_ids", []) for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
