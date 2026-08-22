"""End-to-end entry tests for the first P0 FactCard migration batch."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import direct_rag_node, llm_think_node, route_initial_request, tour_qa_node


class FactCardRuntimeTests(unittest.TestCase):
    def test_pre_tour_opening_hours_uses_fact_card_without_rag_or_model(self):
        state = {"messages": [HumanMessage(content="景区几点开门？")], "performance_metrics": []}
        self.assertEqual(route_initial_request(state), "direct_rag")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            retrieval = direct_rag_node(state)
        rag.invoke.assert_not_called()
        result = llm_think_node({
            **state, **retrieval,
            "messages": [*state["messages"], *retrieval["messages"]],
        })
        self.assertIn("9:00 至 17:30", result["messages"][0].content)
        self.assertIn("17:00", result["messages"][0].content)

    def test_active_tour_refund_and_photo_rules_use_fact_cards_without_state_write(self):
        initial = {
            "tour_state": {"route_status": "touring", "current_stop_id": "label_moon_platform"},
            "tour_interaction_state": {"stop_phase": "explaining"},
            "performance_metrics": [],
        }
        for text, expected in (("买了票之后能退吗？", "当日 18:00 前"), ("园区里可以拍照吗？", "闪光灯")):
            with self.subTest(text=text):
                state = {**initial, "messages": [HumanMessage(content=text)]}
                self.assertEqual(route_initial_request(state), "tour_qa")
                with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                    update = tour_qa_node(state)
                rag.invoke.assert_not_called()
                self.assertIn(expected, update["messages"][0].content)
                self.assertNotIn("tour_state", update)
                self.assertNotIn("tour_interaction_state", update)

    def test_composite_question_renders_confirmed_parts_in_both_entry_modes(self):
        text = "我下午3点到，还能买票进去吗？逛到闭馆来得及吗？"
        pre_tour = {"messages": [HumanMessage(content=text)], "performance_metrics": []}
        self.assertEqual(route_initial_request(pre_tour), "direct_rag")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            retrieval = direct_rag_node(pre_tour)
        rag.invoke.assert_not_called()
        direct = llm_think_node({
            **pre_tour, **retrieval,
            "messages": [*pre_tour["messages"], *retrieval["messages"]],
        })["messages"][0].content

        active = {
            "messages": [HumanMessage(content=text)],
            "tour_state": {"route_status": "touring", "current_stop_id": "label_moon_platform"},
            "tour_interaction_state": {"stop_phase": "explaining"},
            "performance_metrics": [],
        }
        self.assertEqual(route_initial_request(active), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            update = tour_qa_node(active)
        rag.invoke.assert_not_called()
        active_answer = update["messages"][0].content
        for answer in (direct, active_answer):
            self.assertIn("9:00 至 17:30", answer)
            self.assertIn("https://wx.gzcjc.com.cn", answer)
            self.assertIn("能够确认的部分", answer)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)


if __name__ == "__main__":
    unittest.main()
