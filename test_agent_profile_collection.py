"""Offline C2 Agent routing tests for preference collection only."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    journey_mode_selection_node,
    profile_collection_node,
    route_initial_request,
)


def _state(text: str, initial: dict | None = None) -> dict:
    value = dict(initial or {})
    value["messages"] = [HumanMessage(content=text)]
    value["performance_metrics"] = []
    return value


class AgentProfileCollectionTests(unittest.TestCase):
    def test_route_request_with_conflicting_or_unknown_style_fails_closed(self):
        conflict_state = _state(
            "选择定制模式，我有60分钟，选择儿童友好讲解风格和专业讲解风格。"
        )
        self.assertEqual(route_initial_request(conflict_state), "profile_collection")
        conflict = profile_collection_node(conflict_state)
        self.assertEqual(conflict["profile_collection"]["status"], "collecting")
        self.assertIn("多个不同选择", conflict["messages"][0].content)
        self.assertEqual(conflict["visitor_profile"]["explanation_style"], "standard")

        unknown_state = _state(
            "选择定制模式，我有60分钟，选择抽象讲解风格。"
        )
        self.assertEqual(route_initial_request(unknown_state), "profile_collection")
        unknown = profile_collection_node(unknown_state)
        self.assertEqual(unknown["profile_collection"]["status"], "collecting")
        self.assertIn("暂不支持", unknown["messages"][0].content)
        self.assertEqual(unknown["visitor_profile"]["explanation_style"], "standard")
        self.assertNotIn("tour_state", unknown)

    def test_repeat_current_stop_routes_to_controlled_tour_event(self):
        state = _state("请再讲一次当前点。", {
            "tour_state": {
                "route_status": "touring",
                "current_stop_id": "stop_front_courtyard_center",
            },
            "tour_interaction_state": {
                "stop_phase": "explaining",
                "journey_mode": "custom",
            },
        })
        self.assertEqual(route_initial_request(state), "tour_event")

    def test_bare_skip_belongs_to_active_optional_custom_profile_question(self):
        first = profile_collection_node(_state(
            "选择定制模式，安排30分钟路线，我喜欢灰塑"
        ))
        self.assertEqual(
            first["profile_collection"]["next_missing_field"],
            "explanation_style",
        )
        skip_style = _state("跳过", first)
        self.assertEqual(route_initial_request(skip_style), "profile_collection")
        second = profile_collection_node(skip_style)
        self.assertEqual(second["visitor_profile"]["explanation_style"], "standard")
        self.assertEqual(second["profile_collection"]["next_missing_field"], "language")

        skip_language = _state("跳过", second)
        self.assertEqual(route_initial_request(skip_language), "profile_collection")
        ready = profile_collection_node(skip_language)
        self.assertEqual(ready["profile_collection"]["status"], "ready")
        self.assertNotIn("language", ready["visitor_profile"])

    def test_bare_skip_outside_optional_profile_collection_keeps_tour_control(self):
        self.assertEqual(route_initial_request(_state("跳过")), "clarification")

    def test_route_request_missing_fields_enters_collector_before_planning(self):
        state = _state("帮我规划路线")
        self.assertEqual(route_initial_request(state), "journey_mode_selection")
        update = journey_mode_selection_node(state)
        self.assertEqual(update["journey_mode_selection"]["status"], "awaiting_choice")
        self.assertIn("经典模式", update["messages"][0].content)
        self.assertIn("定制模式", update["messages"][0].content)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("active_route_plan", update)

    def test_minimize_walking_request_asks_time_and_keeps_constraint(self):
        state = _state("选择经典模式，给我规划一条少走路的路线")
        self.assertEqual(route_initial_request(state), "profile_collection")
        update = profile_collection_node(state)
        self.assertEqual(
            update["profile_collection"]["next_missing_field"],
            "available_minutes",
        )
        self.assertEqual(
            update["visitor_profile"]["route_constraint"], "minimize_walking"
        )
        self.assertIn("多少分钟", update["messages"][0].content)
        self.assertNotIn("tour_state", update)

    def test_complete_profile_is_saved_without_starting_route(self):
        state = _state("我有30分钟，喜欢灰塑和木雕，简单讲讲，帮我规划路线")
        update = profile_collection_node(state)
        self.assertEqual(update["profile_collection"]["status"], "ready")
        self.assertEqual(update["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(update["visitor_profile"]["interests"], ["灰塑", "木雕"])
        self.assertEqual(update["visitor_profile"]["detail_level"], "short")
        self.assertNotIn("tour_state", update)

    def test_english_minute_route_input_does_not_ask_for_time_again(self):
        state = _state("选择经典模式，30min路线，木雕，详细")
        self.assertEqual(route_initial_request(state), "profile_collection")
        update = profile_collection_node(state)
        self.assertEqual(update["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(update["visitor_profile"]["interests"], ["木雕"])
        self.assertEqual(update["visitor_profile"]["detail_level"], "deep")
        self.assertIn("available_minutes", update["profile_collection"]["resolved_fields"])
        self.assertEqual(update["profile_collection"]["status"], "ready")
        self.assertIsNone(update["profile_collection"]["next_missing_field"])
        self.assertNotIn("多少分钟", update["messages"][0].content)

    def test_active_collection_accepts_next_answer_but_keeps_controlled_fact_routes(self):
        first = profile_collection_node(_state("帮我规划路线"))
        second_state = _state("30分钟", first)
        self.assertEqual(route_initial_request(second_state), "profile_collection")
        second = profile_collection_node(second_state)
        self.assertIsNone(second["profile_collection"]["next_missing_field"])
        self.assertEqual(second["profile_collection"]["required_fields"], ["available_minutes"])
        term_question = _state("灰塑是什么？", second)
        self.assertEqual(route_initial_request(term_question), "tour_qa")
        general_question = _state("陈家祠什么时候建成？", second)
        self.assertEqual(route_initial_request(general_question), "direct_rag")

    def test_arrival_event_keeps_a1_priority_over_active_collection(self):
        initial = profile_collection_node(_state("帮我规划路线"))
        event_state = _state("我到月台了", initial)
        self.assertEqual(route_initial_request(event_state), "tour_event")


if __name__ == "__main__":
    unittest.main()
