"""Offline B4 acceptance tests for the complete StopProgram guidance chain."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    direct_route_node,
    route_after_tour_event,
    route_initial_request,
    stop_guidance_node,
    tour_event_node,
    tour_qa_node,
)
from guide_program_planner import plan_stop_program
from tour_qa import load_guide_cards
from tour_interaction import handle_tour_event


RAG_PAYLOAD = json.dumps(
    {
        "evidence": [
            {
                "document": "07_ornament_crafts.md",
                "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"],
                "source_ids": ["S10"],
                "content": "灰塑是岭南传统建筑装饰工艺，可用于建筑装饰。",
            }
        ]
    },
    ensure_ascii=False,
)


def _state(text: str, initial: dict | None = None) -> dict:
    value = dict(initial or {})
    value["messages"] = [HumanMessage(content=text)]
    value["performance_metrics"] = []
    return value


class StageBEndToEndTests(unittest.TestCase):
    def _started(self) -> dict:
        return direct_route_node(_state("我有30分钟，喜欢灰塑，请规划路线"))

    def _arrived_and_guided(self) -> dict:
        started = self._started()
        arrival_request = _state("我到前院中部了", started)
        self.assertEqual(route_initial_request(arrival_request), "tour_event")
        arrived = tour_event_node(arrival_request)
        state = {**started, **arrived}
        self.assertEqual(route_after_tour_event(state), "stop_guidance")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = RAG_PAYLOAD
            guidance = stop_guidance_node(state)
        return {**state, **guidance}

    def test_each_stop_program_only_selects_its_own_reviewed_ornaments(self):
        cards = load_guide_cards()
        for node_id in ("stop_front_courtyard_center", "label_moon_platform"):
            program = plan_stop_program(node_id, 300, detail_level="deep")
            allowed = {item["ornament_id"] for item in cards[node_id]["ornaments"]}
            self.assertTrue({item.ornament_id for item in program.selected_items}.issubset(allowed))

    def test_detail_budgets_interests_and_output_are_deterministic_without_route_changes(self):
        route_before = self._started()["tour_state"]["route_stop_ids"]
        programs = {
            level: plan_stop_program("stop_front_courtyard_center", 300, ["灰塑"], level)
            for level in ("short", "standard", "deep")
        }
        self.assertEqual([len(programs[level].selected_items) for level in programs], [1, 2, 3])
        self.assertTrue(all(program.allocated_content_seconds <= 300 for program in programs.values()))
        self.assertEqual(
            plan_stop_program("stop_front_courtyard_center", 300, ["灰塑"], "deep").to_dict(),
            programs["deep"].to_dict(),
        )
        self.assertEqual(route_before, self._started()["tour_state"]["route_stop_ids"])

    def test_arrival_guidance_question_restore_and_confirmation_form_one_safe_flow(self):
        state = self._arrived_and_guided()
        self.assertEqual(state["tour_interaction_state"]["stop_phase"], "explaining")
        self.assertEqual(state["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(state["active_stop_program"]["node_id"], "stop_front_courtyard_center")
        self.assertIn("S10", state["messages"][-1].content)

        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = RAG_PAYLOAD
            answer = tour_qa_node(_state("这里的灰塑有什么特点？", state))
        state = {**state, **answer}
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state["tour_interaction_state"], before_interaction)
        self.assertEqual(state["tour_presentation"]["phase"], "explaining")
        self.assertIn("explanation_finished", [item["id"] for item in state["tour_presentation"]["actions"]])

        explained = handle_tour_event(state["tour_state"], state["tour_interaction_state"], "explanation_finished")
        self.assertEqual(explained["tour_state"]["visited_stop_ids"], [])
        completed = handle_tour_event(explained["tour_state"], explained["interaction_state"], "confirm_stop_complete")
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])

    def test_no_evidence_and_empty_future_card_interfaces_do_not_break_basic_guidance(self):
        state = self._started()
        arrived = tour_event_node(_state("我到前院中部了", state))
        state = {**state, **arrived}
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = json.dumps({"evidence": []})
            guidance = stop_guidance_node(state)
        program = guidance["active_stop_program"]
        self.assertIn("未检索到可引用的事实资料", guidance["messages"][0].content)
        self.assertEqual(guidance["retrieved_evidence"], [])
        self.assertTrue(all(not item["research_summary_card_ids"] for item in program["selected_items"]))
        self.assertTrue(all(not item["comparison_card_ids"] for item in program["selected_items"]))
        self.assertEqual(state["tour_state"]["visited_stop_ids"], [])


if __name__ == "__main__":
    unittest.main()
