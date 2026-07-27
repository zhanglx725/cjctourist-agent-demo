"""Offline Agent integration tests for D3 research answers."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import direct_route_node, route_initial_request, tour_event_node, tour_qa_node
from research_card_retrieval import is_explicit_research_question


EVIDENCE = json.dumps({"evidence": [{"document": "07_ornament_crafts.md", "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"], "source_ids": ["S10"], "content": "灰塑以石灰为主料。"}]}, ensure_ascii=False)


def _state(text: str, initial: dict | None = None) -> dict:
    value = dict(initial or {})
    value["messages"] = [HumanMessage(content=text)]
    value["performance_metrics"] = []
    return value


class AgentResearchQaTests(unittest.TestCase):
    def _arrived(self) -> dict:
        started = direct_route_node(_state("我有30分钟，喜欢灰塑，标准讲解，规划路线"))
        arrived = tour_event_node(_state("我到前院中部了", started))
        return {**started, **arrived}

    def test_explicit_research_uses_attributed_card_and_preserves_state(self) -> None:
        state = self._arrived()
        request = _state("从学术研究角度，陈家祠灰塑有什么价值？", state)
        before_tour = deepcopy(state["tour_state"])
        before_profile = deepcopy(state.get("visitor_profile"))
        before_interaction = deepcopy(state["tour_interaction_state"])
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = EVIDENCE
            update = tour_qa_node(request)
        self.assertIn("研究指出", update["messages"][0].content)
        self.assertIn("适用范围与限制", update["messages"][0].content)
        self.assertNotIn("research_008", update["messages"][0].content)
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state.get("visitor_profile"), before_profile)
        self.assertEqual(state["tour_interaction_state"], before_interaction)

    def test_no_eligible_research_summary_safely_keeps_base_evidence(self) -> None:
        state = self._arrived()
        request = _state("从学术研究角度，陈家祠灰塑有什么价值？", state)
        with patch("tour_qa.retrieve_research_cards", return_value={"status": "no_eligible_match", "cards": []}), patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = EVIDENCE
            update = tour_qa_node(request)
        self.assertIn("暂未找到可安全引用", update["messages"][0].content)
        self.assertNotIn("research_", update["messages"][0].content)

    def test_definition_and_comparison_are_not_taken_by_d3(self) -> None:
        state = self._arrived()
        self.assertEqual(route_initial_request(_state("灰塑是什么？", state)), "tour_qa")
        self.assertFalse(is_explicit_research_question("灰塑和砖雕有什么区别？"))
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = EVIDENCE
            update = tour_qa_node(_state("灰塑和砖雕有什么区别？", state))
        self.assertNotIn("从研究视角看", update["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
