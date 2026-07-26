"""Offline unit tests for the A2 point-aware RAG orchestration layer."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question, build_tour_qa_query
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

    def test_current_point_detail_question_is_a_retrieval_hint_and_cites_evidence(self):
        result = answer_tour_question(
            "这里的石雕有什么特点？", self.tour, self.interaction, self._success_search
        )
        self.assertIn("前院中部", result["retrieval_query"])
        self.assertIn("石狮子", result["retrieval_query"])
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

    def test_general_fact_question_is_not_restricted_to_current_point(self):
        result = answer_tour_question(
            "陈家祠什么时候建成？", self.tour, self.interaction, self._success_search
        )
        self.assertIn("用户问题：陈家祠什么时候建成？", result["retrieval_query"])
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

    def test_no_active_tour_keeps_original_query_and_no_presentation(self):
        result = answer_tour_question("灰塑是什么？", None, None, self._success_search)
        self.assertEqual(result["retrieval_query"], "灰塑是什么？")
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


if __name__ == "__main__":
    unittest.main()
