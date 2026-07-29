import json
from copy import deepcopy
import unittest

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import route_initial_request, tour_event_node
from qa_context import create_qa_context
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import (
    answer_qa_follow_up_detail,
    answer_tour_question,
    build_qa_context_from_answer,
)
from tour_state import start_tour


EVIDENCE = {
    "document": "08_ornament_items.md",
    "title_path": ["装饰", "测试条目"],
    "content": "测试资料说明了灰塑装饰的工艺特点。",
    "source_ids": ["S01"],
}


class QaFollowUpTests(unittest.TestCase):
    @staticmethod
    def _search(_: str) -> str:
        return json.dumps({"evidence": [EVIDENCE]}, ensure_ascii=False)

    def setUp(self):
        base = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(base)
        front = handle_tour_event(
            base, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center"
        )
        self.front_tour = front["tour_state"]
        self.front_interaction = front["interaction_state"]

        rear = handle_tour_event(
            self.front_tour, self.front_interaction, "arrive_at_stop", node_id="stop_rear_west_courtyard"
        )
        self.rear_tour = rear["tour_state"]
        self.rear_interaction = rear["interaction_state"]

    def test_explicit_moon_craft_question_is_hard_bounded_but_keeps_physical_location(self):
        before = deepcopy(self.rear_tour)
        result = answer_tour_question(
            "月台上的石雕有什么特点？", self.rear_tour, self.rear_interaction, self._search
        )
        self.assertEqual(result["mode"], "current_point_craft_features")
        self.assertEqual(result["point_context"]["node_id"], "label_moon_platform")
        self.assertEqual(self.rear_tour, before)
        self.assertTrue(result["local_ornaments"])
        self.assertTrue(all(item["craft"] == "石雕" for item in result["local_ornaments"]))
        self.assertIn("您问的是月台", result["message"])

    def test_explicit_craft_features_are_not_downgraded_to_inventory(self):
        result = answer_tour_question(
            "月台上的石雕有什么特点？", self.rear_tour, self.rear_interaction, self._search
        )
        self.assertEqual(result["mode"], "current_point_craft_features")
        self.assertNotIn("inventory", result)

    def test_remote_question_then_detail_requeries_same_explicit_node(self):
        first = answer_tour_question(
            "月台上的石雕有什么特点？", self.rear_tour, self.rear_interaction, self._search
        )
        context = build_qa_context_from_answer("月台上的石雕有什么特点？", first, self.rear_tour)
        before = deepcopy(self.rear_tour)
        detailed = answer_qa_follow_up_detail(
            "再讲详细一点", context, self.rear_tour, self.rear_interaction, self._search
        )
        self.assertEqual(detailed["point_context"]["node_id"], "label_moon_platform")
        self.assertIn("展开说明", detailed["message"])
        self.assertEqual(self.rear_tour, before)
        refreshed = build_qa_context_from_answer(
            "再讲详细一点", detailed, self.rear_tour, context
        )
        self.assertEqual(refreshed["subject_terms"], ("石雕",))
        self.assertTrue(refreshed["follow_up_allowed"])

    def test_current_craft_then_omitted_craft_keeps_same_physical_point(self):
        first = answer_tour_question(
            "这里的灰塑有什么特点？", self.front_tour, self.front_interaction, self._search
        )
        context = build_qa_context_from_answer("这里的灰塑有什么特点？", first, self.front_tour)
        result = answer_qa_follow_up_detail(
            "石雕呢？", context, self.front_tour, self.front_interaction, self._search,
            detailed=False,
        )
        self.assertEqual(result["point_context"]["node_id"], "stop_front_courtyard_center")
        self.assertTrue(all(item["craft"] == "石雕" for item in result["local_ornaments"]))

    def test_here_after_explicit_inventory_returns_to_real_physical_point(self):
        moon = answer_tour_question("月台有什么？", self.rear_tour, self.rear_interaction, self._search)
        context = build_qa_context_from_answer("月台有什么？", moon, self.rear_tour)
        current = answer_tour_question("这里呢？", self.rear_tour, self.rear_interaction, self._search)
        self.assertEqual(context["query_node_id"], "label_moon_platform")
        self.assertEqual(current["mode"], "inventory")
        self.assertEqual(current["point_context"]["node_id"], "stop_rear_west_courtyard")

    def test_missing_context_is_a_clarification_and_never_changes_tour(self):
        before = deepcopy(self.front_tour)
        result = answer_qa_follow_up_detail(
            "再讲详细一点", None, self.front_tour, self.front_interaction, self._search
        )
        self.assertEqual(result["mode"], "qa_follow_up_clarification")
        self.assertEqual(result["evidence"], [])
        self.assertEqual(self.front_tour, before)

    def test_explicit_craft_detail_without_context_uses_whole_site_craft_path(self):
        result = answer_qa_follow_up_detail(
            "请详细讲讲灰塑", None, None, None, self._search
        )
        self.assertEqual(result["mode"], "qa_follow_up_global_craft")
        self.assertIn("灰塑", result["message"])
        self.assertEqual(result["retrieval_query"], "灰塑 是什么 材料 制作流程 陈家祠 题材")

    def test_whole_site_craft_detail_filters_unrelated_service_evidence(self):
        payload = json.dumps(
            {
                "evidence": [
                    EVIDENCE,
                    {
                        "document": "01_basic_info.md",
                        "title_path": ["基础信息", "场馆名称"],
                        "content": "广东民间工艺博物馆提供预约和票务服务。",
                        "source_ids": ["S01"],
                    },
                ]
            },
            ensure_ascii=False,
        )
        result = answer_qa_follow_up_detail(
            "请详细讲讲灰塑", None, None, None, lambda _: payload
        )
        self.assertEqual(len(result["evidence"]), 1)
        self.assertIn("灰塑", result["message"])
        self.assertNotIn("票务", result["message"])
        self.assertNotIn("场馆名称", result["message"])

    def test_whole_site_term_definition_then_detail_retains_the_craft_topic(self):
        first = answer_tour_question("灰塑是什么？", None, None, self._search)
        self.assertEqual(first["mode"], "term_card")
        context = build_qa_context_from_answer("灰塑是什么？", first, None)
        self.assertIsNotNone(context)
        self.assertEqual(context["origin"], "whole_site")
        self.assertIsNone(context["query_node_id"])
        self.assertEqual(context["subject_terms"], ("灰塑",))

        calls = []
        def search(query: str) -> str:
            calls.append(query)
            return self._search(query)

        detailed = answer_qa_follow_up_detail("详细讲讲", context, None, None, search)
        self.assertEqual(detailed["mode"], "qa_follow_up_global_craft")
        self.assertEqual(calls, ["灰塑 是什么 材料 制作流程 陈家祠 题材"])
        self.assertIn("灰塑", detailed["message"])
        self.assertIn("来源：S01", detailed["message"])
        self.assertNotIn("根据本地知识库检索到的资料", detailed["message"])
        self.assertNotIn("08_ornament_items.md", detailed["message"])

    def test_whole_site_term_follow_up_does_not_mutate_active_tour(self):
        first = answer_tour_question("灰塑是什么？", None, None, self._search)
        context = build_qa_context_from_answer("灰塑是什么？", first, None)
        before_tour = deepcopy(self.front_tour)
        before_interaction = deepcopy(self.front_interaction)
        result = answer_qa_follow_up_detail(
            "再讲详细一点", context, self.front_tour, self.front_interaction, self._search
        )
        self.assertEqual(result["mode"], "qa_follow_up_global_craft")
        self.assertEqual(self.front_tour, before_tour)
        self.assertEqual(self.front_interaction, before_interaction)
        self.assertEqual(result["presentation"]["code"], "qa_follow_up_global_craft")

    def test_no_evidence_craft_answer_does_not_create_follow_up_context(self):
        no_evidence = answer_tour_question(
            "这里的灰塑有什么特点？",
            self.front_tour,
            self.front_interaction,
            lambda _: json.dumps({"evidence": []}),
        )
        self.assertEqual(no_evidence["mode"], "current_point_craft_features")
        self.assertEqual(no_evidence["evidence"], [])
        self.assertIsNone(
            build_qa_context_from_answer("这里的灰塑有什么特点？", no_evidence, self.front_tour)
        )

    def test_deictic_inventory_without_a_real_current_stop_clarifies(self):
        result = answer_tour_question("这里呢？", None, None, self._search)
        self.assertEqual(result["mode"], "inventory_error")
        self.assertIsNone(result["point_context"])

    def test_router_preserves_a1_stop_detail_after_stop_guidance(self):
        state = {
            "messages": [
                AIMessage(content="本点讲解", additional_kwargs={"stop_guidance": True}),
                HumanMessage(content="再讲详细一点"),
            ],
            "tour_state": self.front_tour,
            "tour_interaction_state": self.front_interaction,
        }
        self.assertEqual(route_initial_request(state), "tour_event")

    def test_router_uses_read_only_follow_up_only_after_tour_qa(self):
        context = create_qa_context(
            query_node_id="label_moon_platform", origin="explicit_node", subject_kind="craft",
            subject_terms=["石雕"], answer_mode="current_point_craft_features",
            follow_up_allowed=True, physical_node_id_snapshot="stop_rear_west_courtyard",
        )
        state = {
            "messages": [
                AIMessage(content="月台石雕回答", additional_kwargs={"tour_qa_answer": True}),
                HumanMessage(content="再讲详细一点"),
            ],
            "tour_state": self.rear_tour,
            "tour_interaction_state": self.rear_interaction,
            "qa_context": context,
        }
        self.assertEqual(route_initial_request(state), "qa_follow_up_detail")

    def test_tour_event_clears_previous_qa_context(self):
        context = create_qa_context(
            query_node_id="label_moon_platform", origin="explicit_node", subject_kind="craft",
            subject_terms=["石雕"], answer_mode="current_point_craft_features",
            follow_up_allowed=True, physical_node_id_snapshot="stop_rear_west_courtyard",
        )
        state = {
            "messages": [HumanMessage(content="下一站怎么走")],
            "tour_state": self.front_tour,
            "tour_interaction_state": self.front_interaction,
            "qa_context": context,
            "performance_metrics": [],
        }
        updates = tour_event_node(state)
        self.assertIsNone(updates["qa_context"])
        self.assertEqual(updates["tour_state"], self.front_tour)


if __name__ == "__main__":
    unittest.main()
