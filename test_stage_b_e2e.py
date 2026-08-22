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
    route_after_tour_opening,
    route_initial_request,
    stop_guidance_node,
    tour_event_node,
    tour_opening_node,
    tour_qa_node,
)
from guide_program_planner import plan_stop_program
from route_planner import plan_template
from tour_qa import load_guide_cards
from tour_interaction import handle_tour_event, initialize_interaction
from tour_state import start_tour


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
        self.assertEqual(route_after_tour_event(state), "tour_opening")
        opening = tour_opening_node(state)
        self.assertEqual(route_after_tour_opening(opening), "stop_guidance")
        state = {**state, **opening}
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

    def test_thirty_minute_plaster_route_starts_with_front_courtyard_center(self):
        started = self._started()
        self.assertEqual(started["tour_state"]["remaining_stop_ids"][0], "stop_front_courtyard_center")
        self.assertEqual(started["tour_interaction_state"]["pending_stop_id"], "stop_front_courtyard_center")
        self.assertIn("灰塑", started["tour_state"]["interests"])

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
        self.assertNotIn("S10", state["messages"][-1].content)
        self.assertIn(
            "S10",
            {source for entry in state["retrieved_evidence"] for source in entry["source_ids"]},
        )

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

    def test_front_courtyard_message_uses_safe_location_and_hides_internal_fields(self):
        state = self._arrived_and_guided()
        message = state["messages"][-1].content
        program = state["active_stop_program"]
        local_ids = {
            item["ornament_id"]
            for item in load_guide_cards()["stop_front_courtyard_center"]["ornaments"]
        }
        self.assertIn("前院中部", message)
        self.assertTrue({item["ornament_id"] for item in program["selected_items"]}.issubset(local_ids))
        self.assertTrue(any(item.get("observation_location") for item in program["selected_items"]))
        self.assertIn("是一件灰塑装饰", message)
        for internal in ("审核位置", "类型：", "简介：", "planned_seconds", ".md", "项目编辑整理", "未核验"):
            self.assertNotIn(internal, message)

    def test_detail_uses_same_program_and_question_keeps_only_local_instances(self):
        standard_state = self._arrived_and_guided()
        standard_message = standard_state["messages"][-1].content
        before_tour = deepcopy(standard_state["tour_state"])
        before_interaction = deepcopy(standard_state["tour_interaction_state"])

        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = RAG_PAYLOAD
            answer = tour_qa_node(_state("这里的灰塑有什么特点？", standard_state))
        answer_state = {**standard_state, **answer}
        self.assertEqual(answer_state["tour_state"], before_tour)
        self.assertEqual(answer_state["tour_interaction_state"], before_interaction)
        self.assertEqual(answer_state["tour_presentation"]["phase"], "explaining")
        local_names = {
            item["name"]
            for item in load_guide_cards()["stop_front_courtyard_center"]["ornaments"]
            if item["craft"] == "灰塑"
        }
        self.assertTrue(local_names.intersection({"独角狮", "福禄寿", "功名富贵", "松鹤延年"}))
        self.assertNotIn("百鸟朝凤", answer_state["messages"][-1].content)

        detail_event = handle_tour_event(
            answer_state["tour_state"], answer_state["tour_interaction_state"], "request_stop_detail"
        )
        detailed_state = {
            **answer_state,
            "tour_state": detail_event["tour_state"],
            "tour_interaction_state": detail_event["interaction_state"],
            "last_tour_event": {"event": "request_stop_detail", "code": detail_event["code"]},
        }
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = RAG_PAYLOAD
            detailed = stop_guidance_node(detailed_state)
        self.assertNotEqual(standard_message, detailed["messages"][0].content)
        self.assertIn("再看细一点", detailed["messages"][0].content)
        self.assertEqual(detailed_state["tour_state"], before_tour)

    def test_self_arrival_skip_replan_and_last_completion_keep_a1_contract(self):
        tour = start_tour(plan_template("highlights_30"), interests=["灰塑"])
        interaction = initialize_interaction(tour)
        self_arrival = handle_tour_event(
            tour, interaction, "arrive_at_stop", node_id="label_first_main_hall"
        )
        self.assertEqual(self_arrival["code"], "self_arrival")
        self.assertEqual(self_arrival["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(self_arrival["tour_state"]["remaining_stop_ids"], tour["remaining_stop_ids"])

        skipped = handle_tour_event(
            self_arrival["tour_state"], self_arrival["interaction_state"], "skip_stop"
        )
        self.assertEqual(skipped["code"], "skipped")
        self.assertTrue(skipped["tour_state"]["skipped_stop_ids"])
        replanned = handle_tour_event(
            skipped["tour_state"], skipped["interaction_state"], "replan_time", available_minutes=20
        )
        self.assertEqual(replanned["code"], "replanned")
        self.assertFalse(
            set(replanned["tour_state"]["visited_stop_ids"])
            .intersection(replanned["tour_state"]["skipped_stop_ids"])
        )

        final_tour = start_tour(plan_template("highlights_30"))
        final_interaction = initialize_interaction(final_tour)
        for stop_id in list(final_tour["remaining_stop_ids"]):
            arrived = handle_tour_event(final_tour, final_interaction, "arrive_at_stop", node_id=stop_id)
            self.assertNotEqual(arrived["tour_state"]["route_status"], "completed")
            explained = handle_tour_event(
                arrived["tour_state"], arrived["interaction_state"], "explanation_finished"
            )
            final_tour = explained["tour_state"]
            final_interaction = explained["interaction_state"]
            if len(final_tour["remaining_stop_ids"]) == 1:
                self.assertEqual(final_tour["route_status"], "touring")
            completed = handle_tour_event(final_tour, final_interaction, "confirm_stop_complete")
            final_tour = completed["tour_state"]
            final_interaction = completed["interaction_state"]
        self.assertEqual(final_tour["route_status"], "completed")
        self.assertEqual(final_interaction["stop_phase"], "finished")

    def test_no_evidence_and_empty_future_card_interfaces_do_not_break_basic_guidance(self):
        state = self._started()
        arrived = tour_event_node(_state("我到前院中部了", state))
        state = {**state, **arrived}
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = json.dumps({"evidence": []})
            guidance = stop_guidance_node(state)
        program = guidance["active_stop_program"]
        self.assertIn("题材或故事先不急着下结论", guidance["messages"][0].content)
        self.assertEqual(guidance["retrieved_evidence"], [])
        self.assertTrue(all(not item["research_summary_card_ids"] for item in program["selected_items"]))
        self.assertTrue(all(not item["comparison_card_ids"] for item in program["selected_items"]))
        self.assertEqual(state["tour_state"]["visited_stop_ids"], [])


if __name__ == "__main__":
    unittest.main()
