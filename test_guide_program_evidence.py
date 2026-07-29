"""Offline B3 tests: selected objects receive only existing RAG evidence."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from guide_program_evidence import build_stop_guidance
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


EVIDENCE = {
    "document": "08_ornament_items.md",
    "title_path": ["陈家祠建筑装饰条目知识库", "测试装饰"],
    "source_ids": ["S11"],
    "content": "这是可由本地知识库证实的装饰事实。",
}


class GuideProgramEvidenceTests(unittest.TestCase):
    def setUp(self):
        tour = start_tour(plan_template("highlights_30"), interests=["灰塑"], detail_level="standard")
        interaction = initialize_interaction(tour)
        arrived = handle_tour_event(tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        self.tour = arrived["tour_state"]
        self.interaction = arrived["interaction_state"]

    @staticmethod
    def _rag(query: str) -> str:
        return json.dumps({"query": query, "evidence": [EVIDENCE]}, ensure_ascii=False)

    def test_guidance_uses_stop_program_hints_and_rag_evidence_without_state_change(self):
        before_tour = deepcopy(self.tour)
        before_interaction = deepcopy(self.interaction)
        result = build_stop_guidance(self.tour, self.interaction, self._rag)
        self.assertEqual(result["status"], "guided")
        self.assertEqual(result["stop_program"]["node_id"], "stop_front_courtyard_center")
        self.assertEqual(len(result["rag_queries"]), len(result["stop_program"]["selected_items"]))
        self.assertNotIn("S11", result["message"])
        self.assertIn("S11", result["source_ids"])
        self.assertNotIn("08_ornament_items.md", result["message"])
        self.assertIn("08_ornament_items.md", [item["document"] for item in result["evidence"]])
        self.assertEqual(result["presentation"]["phase"], "explaining")
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_no_evidence_is_explicit_and_never_invents_a_fact(self):
        result = build_stop_guidance(self.tour, self.interaction, lambda _: json.dumps({"evidence": []}))
        self.assertEqual(result["status"], "guided_without_evidence")
        self.assertEqual(result["evidence"], [])
        self.assertIn("未检索到可引用的事实资料", result["message"])

    def test_detail_reuses_the_same_deterministic_stop_program_and_keeps_phase(self):
        first = build_stop_guidance(self.tour, self.interaction, self._rag)
        detailed = build_stop_guidance(
            self.tour, self.interaction, self._rag, current_program=first["stop_program"], detailed=True
        )
        self.assertEqual(first["stop_program"], detailed["stop_program"])
        self.assertIn("再看细一点", detailed["message"])
        self.assertEqual(detailed["presentation"]["phase"], "explaining")

    def test_self_arrival_cannot_be_used_as_a_formal_stop_explanation(self):
        initial = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(initial)
        self_arrival = handle_tour_event(initial, interaction, "arrive_at_stop", node_id="label_first_main_hall")
        result = build_stop_guidance(self_arrival["tour_state"], self_arrival["interaction_state"], self._rag)
        self.assertEqual(result["status"], "inactive_stop")
        self.assertEqual(result["evidence"], [])

    def test_rag_exception_is_safe_and_keeps_program_auditable(self):
        result = build_stop_guidance(
            self.tour, self.interaction, lambda _: (_ for _ in ()).throw(RuntimeError("offline"))
        )
        self.assertEqual(result["status"], "guided_without_evidence")
        self.assertIsNotNone(result["stop_program"])
        self.assertIn("不据名称扩写", result["message"])


if __name__ == "__main__":
    unittest.main()
