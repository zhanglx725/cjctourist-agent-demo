"""Offline Agent integration tests for A2 route selection and state safety."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import (
    direct_rag_node,
    direct_route_node,
    llm_think_node,
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

COLOR_PAINTING_PAYLOAD = json.dumps(
    {
        "evidence": [
            {
                "document": "07_ornament_crafts.md",
                "title_path": ["陈家祠建筑装饰工艺总览", "彩绘：门神、壁画与楹联"],
                "source_ids": ["S10"],
                "content": (
                    "- **门神**：陈氏书院大门设有气势威武的彩绘门神，是建筑入口的重要视觉与守护性装饰。 "
                    "- **壁画**：东西厢房绘有多幅壁画，馆方列举的题材包括滕王阁图、夜宴桃李。 "
                    "- **楹联**：书院楹联主要颂扬和缅怀祖先功绩，表达光大先祖文风宏业的理想与愿望。"
                ),
            }
        ]
    },
    ensure_ascii=False,
)
HISTORY_PAYLOAD = json.dumps(
    {
        "evidence": [
            {
                "category": "history_architecture",
                "document": "02_history_architecture.md",
                "title_path": ["历史、建筑与文化特色", "历史沿革"],
                "source_ids": ["S02", "S04"],
                "content": (
                    "1888 年，陈氏书院建祠公所成立并开始筹建。"
                    "馆方历史页面写“1893 年落成”；"
                    "广州市文化广电旅游局页面写“1888 年筹建、1894 年建成”。"
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

    def test_no_route_single_fact_keeps_direct_rag_path_but_skips_llm_rendering(self):
        request = _message_state("陈家祠什么时候建成？")
        self.assertEqual(route_initial_request(request), "direct_rag")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = HISTORY_PAYLOAD
            retrieval = direct_rag_node(request)
        rag.invoke.assert_called_once_with(
            {
                "query": "陈家祠 1888年筹建 1893年落成 1894年建成 来源差异",
                "categories": ["history_architecture"],
            }
        )
        next_state = {
            **request,
            **retrieval,
            "messages": [*request["messages"], *retrieval["messages"]],
        }
        with patch("agent_graph.build_model") as build_model:
            answer = llm_think_node(next_state)
        build_model.assert_not_called()
        message = answer["messages"][0].content
        self.assertIn("1888 年开始筹建", message)
        self.assertIn("1893 年落成", message)
        self.assertIn("1894 年建成", message)
        self.assertNotIn("02_history_architecture.md", message)
        self.assertEqual(
            answer["performance_metrics"][-1]["phase"],
            "deterministic_single_fact_answer",
        )

    def test_active_tour_single_fact_uses_same_answer_first_renderer(self):
        state = self._arrived_tour()
        request = _message_state("陈家祠哪一年建成？", state)
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = HISTORY_PAYLOAD
            update = tour_qa_node(request)
        rag.invoke.assert_called_once_with(
            {
                "query": "陈家祠 1888年筹建 1893年落成 1894年建成 来源差异",
                "categories": ["history_architecture"],
            }
        )
        message = update["messages"][0].content
        self.assertIn("1888 年开始筹建", message)
        self.assertIn("1893 年落成", message)
        self.assertIn("1894 年建成", message)
        self.assertNotIn("02_history_architecture.md", message)
        self.assertEqual(
            update["tour_presentation"]["code"],
            "tour_qa_single_fact_answer",
        )

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
        rag.invoke.assert_not_called()
        self.assertIn("珠江三角洲传统建筑", update["messages"][0].content)
        self.assertIn("草筋灰或纸筋灰", update["messages"][0].content)
        self.assertNotIn("07_ornament_crafts.md", update["messages"][0].content)

    def test_explicit_craft_detail_routes_to_tour_qa_without_prior_context(self):
        request = _message_state("请详细讲讲灰塑")
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            update = tour_qa_node(request)
        rag.invoke.assert_not_called()
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
        rag.invoke.assert_not_called()
        self.assertIn("灰塑", update["messages"][0].content)
        self.assertNotIn("08_ornament_items.md", update["messages"][0].content)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)

    def test_pottery_detail_explanation_follow_up_uses_canonical_craft_path(self):
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            first = tour_qa_node(_message_state("陶塑是什么？"))
        rag.invoke.assert_not_called()
        self.assertEqual(first["qa_context"]["subject_terms"], ("陶塑",))
        follow = {
            **first,
            "messages": [
                first["messages"][0],
                HumanMessage(content="详细讲解"),
            ],
            "performance_metrics": [],
        }
        self.assertEqual(route_initial_request(follow), "qa_follow_up_detail")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = CRAFT_PAYLOAD
            update = qa_follow_up_detail_node(follow)
        rag.invoke.assert_not_called()
        answer = update["messages"][0].content
        self.assertIn("陶塑", answer)
        self.assertIn("十一条陶塑脊饰", answer)
        self.assertNotIn("07_ornament_crafts.md", answer)
        self.assertNotIn("DSML", answer)

    def test_all_seven_crafts_use_the_scoped_craft_path(self):
        from tour_qa import CRAFT_TERMS
        self.assertEqual(
            CRAFT_TERMS,
            ("陶塑", "灰塑", "木雕", "石雕", "砖雕", "铜铁铸", "彩绘"),
        )

    def test_colored_painting_short_and_detail_answers_are_narrative_not_raw_chunks(self):
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = COLOR_PAINTING_PAYLOAD
            brief = tour_qa_node(_message_state("彩绘是什么？"))
        self.assertIn("门神", brief["messages"][0].content)
        self.assertIn("壁画", brief["messages"][0].content)
        self.assertNotIn("- **", brief["messages"][0].content)
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = COLOR_PAINTING_PAYLOAD
            detailed = tour_qa_node(_message_state("请详细讲讲彩绘"))
        self.assertIn("楹联", detailed["messages"][0].content)
        self.assertIn("完整来看", detailed["messages"][0].content)
        self.assertNotIn("07_ornament_crafts.md", detailed["messages"][0].content)

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
