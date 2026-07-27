"""Offline D4 Agent integration tests."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import direct_route_node, route_initial_request, tour_event_node, tour_qa_node


EVIDENCE = json.dumps({"evidence": [{"document": "07_ornament_crafts.md", "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"], "source_ids": ["S10"], "content": "灰塑以石灰为主料。"}]}, ensure_ascii=False)


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class AgentComparisonQaTests(unittest.TestCase):
    def _arrived(self) -> dict:
        started = direct_route_node(_state("我有30分钟，喜欢灰塑，标准讲解，规划路线"))
        arrived = tour_event_node(_state("我到前院中部了", started))
        return {**started, **arrived}

    def test_general_comparison_falls_back_without_research_card_leak(self) -> None:
        state = self._arrived()
        request = _state("灰塑和砖雕有什么区别？", state)
        before_tour = deepcopy(state["tour_state"])
        before_profile = deepcopy(state.get("visitor_profile"))
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = EVIDENCE
            update = tour_qa_node(request)
        self.assertIn("基础资料", update["messages"][0].content)
        self.assertNotIn("research_only", update["messages"][0].content)
        self.assertNotIn("cmp_", update["messages"][0].content)
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state.get("visitor_profile"), before_profile)

    def test_research_comparison_is_attributed_and_keeps_limits(self) -> None:
        state = self._arrived()
        request = _state("从学术研究角度比较广州灰塑和山东鄄城砖塑。", state)
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = EVIDENCE
            update = tour_qa_node(request)
        self.assertIn("相关研究", update["messages"][0].content)
        self.assertIn("适用范围与限制", update["messages"][0].content)
        self.assertNotIn("comparison_id", update["messages"][0].content)

    def test_unresolved_pronoun_clarifies_without_rag_or_state_change(self) -> None:
        state = self._arrived()
        request = _state("它们有什么相同点？", state)
        before = deepcopy(state["tour_state"])
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            update = tour_qa_node(request)
        rag.invoke.assert_not_called()
        self.assertIn("缺少可核对的两个比较对象", update["messages"][0].content)
        self.assertEqual(state["tour_state"], before)


if __name__ == "__main__":
    unittest.main()
