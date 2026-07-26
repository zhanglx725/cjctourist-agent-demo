"""Offline C2 Agent routing tests for preference collection only."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import profile_collection_node, route_initial_request


def _state(text: str, initial: dict | None = None) -> dict:
    value = dict(initial or {})
    value["messages"] = [HumanMessage(content=text)]
    value["performance_metrics"] = []
    return value


class AgentProfileCollectionTests(unittest.TestCase):
    def test_route_request_missing_fields_enters_collector_before_planning(self):
        state = _state("帮我规划路线")
        self.assertEqual(route_initial_request(state), "profile_collection")
        update = profile_collection_node(state)
        self.assertEqual(update["profile_collection"]["next_missing_field"], "available_minutes")
        self.assertNotIn("tour_state", update)
        self.assertNotIn("active_route_plan", update)

    def test_complete_profile_is_saved_without_starting_route(self):
        state = _state("我有30分钟，喜欢灰塑和木雕，简单讲讲，帮我规划路线")
        update = profile_collection_node(state)
        self.assertEqual(update["profile_collection"]["status"], "ready")
        self.assertEqual(update["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(update["visitor_profile"]["interests"], ["木雕", "灰塑"])
        self.assertEqual(update["visitor_profile"]["detail_level"], "short")
        self.assertNotIn("tour_state", update)

    def test_active_collection_accepts_next_answer_but_questions_keep_rag_route(self):
        first = profile_collection_node(_state("帮我规划路线"))
        second_state = _state("30分钟", first)
        self.assertEqual(route_initial_request(second_state), "profile_collection")
        second = profile_collection_node(second_state)
        self.assertEqual(second["profile_collection"]["next_missing_field"], "interests")
        question_state = _state("灰塑是什么？", second)
        self.assertEqual(route_initial_request(question_state), "direct_rag")

    def test_arrival_event_keeps_a1_priority_over_active_collection(self):
        initial = profile_collection_node(_state("帮我规划路线"))
        event_state = _state("我到月台了", initial)
        self.assertEqual(route_initial_request(event_state), "tour_event")


if __name__ == "__main__":
    unittest.main()
