"""Offline Agent integration tests for A2 route selection and state safety."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import (
    direct_route_node,
    qa_follow_up_detail_node,
    route_initial_request,
    tour_event_node,
    tour_qa_node,
)


FAKE_PAYLOAD = json.dumps(
    {
        "evidence": [
            {
                "document": "08_ornament_items.md",
                "title_path": ["陈家祠建筑装饰条目知识库", "独角狮"],
                "source_ids": ["S11"],
                "content": "独角狮为灰塑建筑装饰题材。",
            }
        ]
    },
    ensure_ascii=False,
)

CRAFT_PAYLOAD = json.dumps(
    {
        "evidence": [
            {
                "document": "07_ornament_crafts.md",
                "title_path": ["陈家祠建筑装饰工艺总览", "灰塑：岭南建筑的现场堆塑艺术"],
                "source_ids": ["S10"],
                "content": (
                    "- **工艺性质与位置**：灰塑是珠江三角洲传统建筑中广泛使用的装饰艺术。 "
                    "- **材料与流程**：艺人以石灰为主料，加入发酵后的稻草或草纸，"
                    "制成草筋灰或纸筋灰；通常先用草筋灰堆塑造型，再用纸筋灰细塑表面，"
                    "干燥到一定程度后施彩。"
                ),
            }
        ]
    },
    ensure_ascii=False,
)


def _message_state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class AgentTourQaTests(unittest.TestCase):
    def _arrived_tour(self) -> dict:
        started = direct_route_node(_message_state("我有30分钟，帮我规划路线"))
        arrival = tour_event_node(_message_state("我到前院中部了", started))
        return {**started, **arrival}

    def test_active_tour_detail_question_routes_to_tour_qa_without_state_change(self):
        state = self._arrived_tour()
        request = _message_state("这里的石雕有什么特点？", state)
        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = FAKE_PAYLOAD
            update = tour_qa_node(request)
        self.assertGreaterEqual(rag.invoke.call_count, 2)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state["tour_interaction_state"], before_interaction)
        self.assertEqual(update["tour_presentation"]["phase"], "explaining")
        self.assertIn("S11", update["messages"][0].content)
        self.assertIn("工艺特点", update["messages"][0].content)
        self.assertNotIn("根据本地知识库检索到的资料：", update["messages"][0].content)

    def test_explicit_point_inventory_routes_to_tour_qa_without_active_route(self):
        request = _message_state("月台有哪些装饰？")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            update = tour_qa_node(request)
        rag.invoke.assert_not_called()
        self.assertIn("月台", update["messages"][0].content)
        self.assertIn("杏林春燕", update["messages"][0].content)

    def test_explicit_point_inventory_uses_tour_qa_without_active_route(self):
        request = _message_state("月台有什么？")
        self.assertEqual(route_initial_request(request), "tour_qa")

    def test_arrival_text_remains_event_not_rag(self):
        state = self._arrived_tour()
        self.assertEqual(route_initial_request(_message_state("我到月台了", state)), "tour_event")

    def test_reviewed_term_routes_to_tour_qa_and_comparison_does_not(self):
        state = self._arrived_tour()
        self.assertEqual(route_initial_request(_message_state("灰塑英文怎么说？", state)), "tour_qa")
        self.assertEqual(route_initial_request(_message_state("灰塑和砖雕有什么区别？", state)), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = FAKE_PAYLOAD
            term = tour_qa_node(_message_state("灰塑英文怎么说？", state))
            comparison = tour_qa_node(_message_state("灰塑和砖雕有什么区别？", state))
        self.assertIn("lime-plaster relief", term["messages"][0].content)
        self.assertGreaterEqual(rag.invoke.call_count, 1)

    def test_term_without_route_uses_controlled_tour_qa(self):
        request = _message_state("灰塑是什么？")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            update = tour_qa_node(request)
        rag.invoke.assert_called_once_with({"query": "灰塑 工艺性质 材料与流程 陈家祠"})
        self.assertIn("以石灰为主料", update["messages"][0].content)
        self.assertIn("草筋灰或纸筋灰", update["messages"][0].content)

    def test_explicit_craft_detail_routes_to_tour_qa_without_prior_context(self):
        request = _message_state("请详细讲讲灰塑")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            update = tour_qa_node(request)
        rag.invoke.assert_called_once_with({"query": "灰塑 工艺性质 材料与流程 陈家祠"})
        self.assertIn("灰塑", update["messages"][0].content)
        self.assertEqual(update["qa_context"]["origin"], "whole_site")

    def test_whole_site_term_detail_follow_up_keeps_subject_without_a_route(self):
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            first = tour_qa_node(_message_state("灰塑是什么？"))
        self.assertEqual(first["qa_context"]["subject_terms"], ("灰塑",))
        follow = {
            **first,
            "messages": [
                first["messages"][0],
                HumanMessage(content="详细讲讲"),
            ],
            "performance_metrics": [],
        }
        self.assertEqual(route_initial_request(follow), "qa_follow_up_detail")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            update = qa_follow_up_detail_node(follow)
        rag.invoke.assert_called_once_with({"query": "灰塑 工艺性质 材料与流程 陈家祠"})
        self.assertIn("灰塑", update["messages"][0].content)
        self.assertNotIn("08_ornament_items.md", update["messages"][0].content)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)

    def test_unsafe_photo_request_still_enters_controlled_photo_qa_path(self):
        request = _message_state("我想踩在栏杆上拍照，怎么拍？")
        self.assertEqual(route_initial_request(request), "tour_qa")

    def test_unsafe_photo_request_beats_arrival_without_partial_state_update(self):
        state = self._arrived_tour()
        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        request = _message_state("我到月台了，踩栏杆怎么拍？", state)
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            update = tour_qa_node(request)
        rag.invoke.assert_not_called()
        self.assertIn("不建议", update["messages"][0].content)
        self.assertNotIn("月台", update["messages"][0].content.split("\n")[0])
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state["tour_interaction_state"], before_interaction)

    def test_ordinary_railing_fact_is_not_a_photo_safety_refusal(self):
        state = self._arrived_tour()
        request = _message_state("栏杆有什么特点？", state)
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = FAKE_PAYLOAD
            update = tour_qa_node(request)
        self.assertNotIn("不建议踩、爬", update["messages"][0].content)

    def test_answered_question_does_not_block_later_a1_event(self):
        state = self._arrived_tour()
        request = _message_state("前院中部有什么？", state)
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = FAKE_PAYLOAD
            qa_update = tour_qa_node(request)
        continued = {**state, **qa_update}
        event_update = tour_event_node(_message_state("讲完了，去下一站", continued))
        self.assertEqual(event_update["last_tour_intent"]["event_type"], "confirm_stop_complete")
        self.assertEqual(event_update["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])


if __name__ == "__main__":
    unittest.main()
