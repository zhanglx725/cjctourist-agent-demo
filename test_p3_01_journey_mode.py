"""P3-01 contract tests for session-owned classic/custom journey modes."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    _read_only_resume_target,
    direct_route_node,
    profile_collection_node,
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


class JourneyModeContractTests(unittest.TestCase):
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
            ["available_minutes", "interests"],
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

        ready = profile_collection_node(_state(
            "\u6211\u559c\u6b22\u7070\u5851\uff0c\u5e2e\u6211\u89c4\u5212", first
        ))
        self.assertEqual(ready["profile_collection"]["status"], "ready")
        self.assertEqual(
            ready["profile_collection"]["required_fields"],
            ["available_minutes", "interests"],
        )
        self.assertNotIn("journey_mode", ready["visitor_profile"])
        self.assertEqual(ready["visitor_profile"]["detail_level"], "standard")

    def test_custom_mode_is_captured_only_as_non_computational_route_audit(self):
        collected = profile_collection_node(_state(
            "选择定制模式，我有30分钟，喜欢灰塑，标准讲解，帮我规划路线"
        ))
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
