"""Offline integration tests for B3 Agent graph stop-guidance wiring."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    direct_route_node,
    route_after_tour_event,
    route_after_tour_opening,
    stop_guidance_node,
    tour_event_node,
    tour_opening_node,
)


PAYLOAD = json.dumps({
    "evidence": [{
        "document": "07_ornament_crafts.md", "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"],
        "source_ids": ["S10"], "content": "灰塑是岭南传统建筑装饰工艺。",
    }]
}, ensure_ascii=False)


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class AgentStopGuidanceTests(unittest.TestCase):
    def _arrived(self):
        started = direct_route_node(_state("我有30分钟，请规划路线"))
        arrived = tour_event_node(_state("我到前院中部了", started))
        state = {**started, **arrived}
        self.assertEqual(route_after_tour_event(state), "tour_opening")
        opening = tour_opening_node(state)
        self.assertEqual(route_after_tour_opening(opening), "stop_guidance")
        return {**state, **opening}

    def test_planned_arrival_opens_then_routes_to_guidance_without_marking_visit(self):
        state = self._arrived()
        self.assertEqual(state["tour_opening_program"]["status"], "played")
        before_tour = deepcopy(state["tour_state"])
        before_interaction = deepcopy(state["tour_interaction_state"])
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = PAYLOAD
            update = stop_guidance_node(state)
        self.assertGreaterEqual(rag.invoke.call_count, 1)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state["tour_interaction_state"], before_interaction)
        self.assertEqual(update["tour_presentation"]["phase"], "explaining")
        self.assertNotIn("S10", update["messages"][0].content)
        self.assertIn("S10", {source for entry in update["retrieved_evidence"] for source in entry["source_ids"]})
        self.assertTrue(update["active_stop_program"]["guidance_policy"]["fact_evidence_required"])
        self.assertEqual(
            update["active_stop_program"]["guidance_policy"]["budget_cap_mode"],
            "min_with_stop_budget",
        )

    def test_request_detail_reaches_guidance_and_keeps_route_progress(self):
        state = self._arrived()
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = PAYLOAD
            first = stop_guidance_node(state)
        detailed_event = tour_event_node(_state("再讲详细一点", {**state, **first}))
        continued = {**state, **first, **detailed_event}
        self.assertEqual(route_after_tour_event(continued), "stop_guidance")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = PAYLOAD
            detailed = stop_guidance_node(continued)
        self.assertEqual(detailed_event["tour_state"]["visited_stop_ids"], [])
        self.assertIn("再看细一点", detailed["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
