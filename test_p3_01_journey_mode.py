"""P3-01 contract tests for session-owned classic/custom journey modes."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    _read_only_resume_target,
    direct_route_node,
    journey_mode_selection_node,
    profile_collection_node,
    route_after_journey_mode_selection,
    route_initial_request,
)
from route_planner import plan_template
from tour_interaction import (
    explicit_journey_mode_choice,
    handle_tour_event,
    initialize_interaction,
    update_session_control,
)
from tour_state import start_tour


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


def _finish_custom_optional(state: dict) -> dict:
    value = state
    if value["profile_collection"]["next_missing_field"] == "explanation_style":
        value = profile_collection_node(_state("标准风格", value))
    if value["profile_collection"]["next_missing_field"] == "language":
        value = profile_collection_node(_state("英语", value))
    return value


class JourneyModeContractTests(unittest.TestCase):
    def test_standalone_enter_custom_mode_never_falls_through_to_llm(self):
        state = _state("进入定制模式")
        self.assertEqual(route_initial_request(state), "journey_mode_selection")
        selected = journey_mode_selection_node(state)
        self.assertEqual(
            selected["journey_mode_selection"],
            {"status": "selected", "selected_mode": "custom"},
        )
        self.assertEqual(route_after_journey_mode_selection(selected), "profile_collection")

    def test_unspecified_route_request_requires_explicit_mode_selection(self):
        initial = _state("我现在想规划路线。")
        self.assertEqual(route_initial_request(initial), "journey_mode_selection")
        prompted = journey_mode_selection_node(initial)
        self.assertEqual(
            prompted["journey_mode_selection"]["status"], "awaiting_choice"
        )
        self.assertIn("经典模式", prompted["messages"][0].content)
        self.assertIn("定制模式", prompted["messages"][0].content)

        choice_state = _state("选择定制模式", prompted)
        self.assertEqual(route_initial_request(choice_state), "journey_mode_selection")
        selected = journey_mode_selection_node(choice_state)
        self.assertEqual(route_after_journey_mode_selection(selected), "profile_collection")
        self.assertEqual(
            selected["tour_interaction_state"]["journey_mode"], "custom"
        )
        collecting = profile_collection_node(_state("选择定制模式", selected))
        self.assertEqual(
            collecting["profile_collection"]["next_missing_field"],
            "available_minutes",
        )
        self.assertNotIn("tour_state", collecting)

    def test_custom_mode_and_duration_shorthands_start_profile_collection(self):
        for text in (
            "定制，60min",
            "定制模式，60分钟",
            "选择定制模式，60分钟",
        ):
            with self.subTest(text=text):
                state = _state(text)
                self.assertEqual(route_initial_request(state), "profile_collection")
                update = profile_collection_node(state)
                self.assertEqual(
                    update["tour_interaction_state"]["journey_mode"], "custom"
                )
                self.assertEqual(update["visitor_profile"]["available_minutes"], 60)
                self.assertEqual(
                    update["profile_collection"]["next_missing_field"], "interests"
                )
                self.assertNotIn("tour_state", update)

    def test_legacy_tour_mode_is_preserved_and_journey_mode_is_separate(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(
            tour, tour_mode="button_guided", journey_mode="custom"
        )
        self.assertEqual(interaction["tour_mode"], "button_guided")
        self.assertEqual(interaction["journey_mode"], "custom")
        self.assertEqual(interaction["resume_after_read_only"], "guided_tour")

    def test_classic_default_requires_only_time_and_never_writes_visitor_profile_mode(self):
        update = profile_collection_node(_state("我有30分钟，帮我规划路线"))
        self.assertEqual(update["tour_interaction_state"]["journey_mode"], "classic")
        self.assertEqual(update["profile_collection"]["required_fields"], ["available_minutes"])
        self.assertEqual(update["profile_collection"]["status"], "ready")
        self.assertNotIn("journey_mode", update["visitor_profile"])
        self.assertNotIn("tour_mode", update["visitor_profile"])
        self.assertNotIn("tour_state", update)

    def test_custom_requires_explicit_mode_choice_and_collects_explicit_preferences(self):
        update = profile_collection_node(_state("选择定制模式，帮我规划路线"))
        self.assertEqual(update["tour_interaction_state"]["journey_mode"], "custom")
        self.assertEqual(
            update["profile_collection"]["required_fields"],
            ["available_minutes", "interests", "explanation_style", "language"],
        )
        self.assertEqual(update["profile_collection"]["next_missing_field"], "available_minutes")
        self.assertEqual(explicit_journey_mode_choice("我喜欢灰塑，讲详细一点"), None)

    def test_custom_collects_time_and_interests_without_a_depth_question(self):
        first = profile_collection_node(_state(
            "\u9009\u62e9\u5b9a\u5236\u6a21\u5f0f\uff0c\u6211\u670930\u5206\u949f"
        ))
        self.assertEqual(first["profile_collection"]["next_missing_field"], "interests")
        self.assertNotIn("\u8bb2\u89e3\u6df1\u5ea6", first["messages"][0].content)
        self.assertNotIn("\u7b80\u7565\u8fd8\u662f\u8be6\u7ec6", first["messages"][0].content)

        interests = profile_collection_node(_state(
            "\u6211\u559c\u6b22\u7070\u5851\uff0c\u5e2e\u6211\u89c4\u5212", first
        ))
        self.assertEqual(interests["profile_collection"]["next_missing_field"], "explanation_style")
        style = profile_collection_node(_state("故事风格", interests))
        self.assertEqual(style["profile_collection"]["next_missing_field"], "language")
        ready = profile_collection_node(_state("跳过", style))
        self.assertEqual(ready["profile_collection"]["status"], "ready")
        self.assertEqual(
            ready["profile_collection"]["required_fields"],
            ["available_minutes", "interests", "explanation_style", "language"],
        )
        self.assertNotIn("journey_mode", ready["visitor_profile"])
        self.assertEqual(ready["visitor_profile"]["detail_level"], "standard")
        self.assertEqual(ready["visitor_profile"]["explanation_style"], "story")
        self.assertNotIn("language", ready["visitor_profile"])

    def test_custom_accepts_typed_style_language_and_independent_skips(self):
        first = profile_collection_node(_state("选择定制模式，我有45分钟，喜欢木雕"))
        self.assertEqual(first["profile_collection"]["next_missing_field"], "explanation_style")
        styled = profile_collection_node(_state("我喜欢互动问答风格", first))
        self.assertEqual(styled["visitor_profile"]["explanation_style"], "interactive")
        self.assertEqual(styled["profile_collection"]["next_missing_field"], "language")
        korean = profile_collection_node(_state("韩语", styled))
        self.assertEqual(korean["profile_collection"]["status"], "ready")
        self.assertEqual(korean["visitor_profile"]["language"], "ko")

        second = profile_collection_node(_state("选择定制模式，我有30分钟，喜欢灰塑"))
        skipped_style = profile_collection_node(_state("跳过", second))
        self.assertEqual(skipped_style["visitor_profile"]["explanation_style"], "standard")
        free_language = profile_collection_node(_state("泰语", skipped_style))
        self.assertEqual(free_language["visitor_profile"]["language"], "泰语")

    def test_one_turn_style_phrases_do_not_contaminate_interests(self):
        cases = {
            "故事风格": "story",
            "技术风格": "technical",
            "互动问答风格": "interactive",
            "专家风格": "expert",
            "标准风格": "standard",
        }
        for phrase, expected_style in cases.items():
            with self.subTest(phrase=phrase):
                result = profile_collection_node(_state(
                    "选择定制模式，安排45分钟路线，我喜欢木雕和灰塑，"
                    f"希望使用{phrase}，讲解语言选择英语"
                ))
                self.assertEqual(result["profile_collection"]["status"], "ready")
                self.assertEqual(result["visitor_profile"]["interests"], ["木雕", "灰塑"])
                self.assertEqual(
                    result["visitor_profile"]["explanation_style"], expected_style
                )
                self.assertEqual(result["visitor_profile"]["language"], "en")

        interest_only = profile_collection_node(_state(
            "选择定制模式，我有45分钟，对三国故事感兴趣"
        ))
        self.assertEqual(interest_only["visitor_profile"]["interests"], ["三国", "故事"])
        self.assertEqual(
            interest_only["profile_collection"]["next_missing_field"],
            "explanation_style",
        )

    def test_custom_mode_is_captured_only_as_non_computational_route_audit(self):
        collected = profile_collection_node(_state(
            "选择定制模式，我有30分钟，喜欢灰塑，标准讲解，帮我规划路线"
        ))
        collected = _finish_custom_optional(collected)
        route = direct_route_node(_state("继续", collected))
        audit = route["active_route_plan"]["journey_mode_audit"]
        self.assertEqual(audit["selected_mode"], "custom")
        self.assertFalse(audit["used_for_route_calculation"])
        self.assertEqual(route["tour_interaction_state"]["journey_mode"], "custom")
        self.assertNotIn("journey_mode", route["tour_state"])
        self.assertNotIn("journey_mode", route["visitor_profile"])

    def test_custom_detail_policy_is_derived_not_persisted_in_profile_or_route(self):
        collected = profile_collection_node(_state(
            "\u9009\u62e9\u5b9a\u5236\u6a21\u5f0f\uff0c\u6211\u670930\u5206\u949f\uff0c\u559c\u6b22\u7070\u5851\uff0c\u5e2e\u6211\u89c4\u5212"
        ))
        collected = _finish_custom_optional(collected)
        route = direct_route_node(_state("\u7ee7\u7eed", collected))
        self.assertEqual(route["visitor_profile"]["detail_level"], "standard")
        self.assertNotIn("journey_mode", route["visitor_profile"])
        self.assertFalse(route["active_route_plan"]["journey_mode_audit"]["used_for_route_calculation"])
        self.assertEqual(route["tour_interaction_state"]["journey_mode"], "custom")

    def test_read_only_interruption_reads_session_resume_without_writing_state(self):
        collecting = profile_collection_node(_state("帮我规划路线"))
        before_profile = dict(collecting["visitor_profile"])
        self.assertEqual(_read_only_resume_target(collecting), "profile_collection")
        self.assertEqual(
            collecting["tour_interaction_state"]["resume_after_read_only"],
            "profile_collection",
        )
        self.assertEqual(collecting["visitor_profile"], before_profile)
        other_thread = update_session_control(None)
        self.assertEqual(other_thread["journey_mode"], "classic")
        self.assertIsNone(other_thread["resume_after_read_only"])

    def test_invalid_session_mode_fails_closed_to_transparent_classic_default(self):
        self.assertEqual(
            update_session_control({"journey_mode": "not_a_mode"})["journey_mode"],
            "classic",
        )

    def test_finishing_a_tour_clears_session_mode_but_not_route_fact(self):
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour, journey_mode="custom")
        finished = handle_tour_event(tour, interaction, "finish_tour")
        self.assertTrue(finished["ok"])
        self.assertEqual(finished["interaction_state"]["journey_mode"], "classic")
        self.assertIsNone(finished["interaction_state"]["resume_after_read_only"])
        self.assertEqual(finished["tour_state"]["route_status"], "completed")


if __name__ == "__main__":
    unittest.main()
