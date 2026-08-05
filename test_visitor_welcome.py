from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import (
    route_after_visitor_onboarding,
    route_after_visitor_welcome,
    route_initial_request,
    visitor_onboarding_node,
    visitor_welcome_node,
)
from visitor_welcome import LANGUAGE_PROMPT, MODE_PROMPT, WELCOME_MESSAGE


class VisitorWelcomeTests(unittest.TestCase):
    def test_new_thread_receives_exact_bilingual_welcome_once(self):
        first = visitor_welcome_node({"performance_metrics": []})
        self.assertEqual(first["messages"][0].content, WELCOME_MESSAGE)
        self.assertEqual(first["visitor_welcome_program"]["status"], "awaiting_ready")
        self.assertEqual(first["visitor_welcome_program"]["play_count"], 1)
        second = visitor_welcome_node(first)
        self.assertNotIn("messages", second)

    def test_empty_bootstrap_ends_after_welcome(self):
        state = {
            "messages": [AIMessage(content=WELCOME_MESSAGE)],
            "visitor_welcome_program": {"schema_version": "visitor_welcome_v1", "status": "awaiting_ready"},
        }
        self.assertEqual(route_after_visitor_welcome(state), "__end__")

    def test_first_user_message_continues_after_welcome_without_being_swallowed(self):
        state = {
            "messages": [
                HumanMessage(content="经典模式"),
                AIMessage(content=WELCOME_MESSAGE),
            ],
            "visitor_welcome_program": {"schema_version": "visitor_welcome_v1", "status": "awaiting_ready"},
        }
        self.assertEqual(route_after_visitor_welcome(state), "semantic_normalization")

    def test_ready_language_and_classic_mode_complete_onboarding(self):
        ready = visitor_onboarding_node({
            "messages": [HumanMessage(content="I'm ready")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_ready",
            },
            "performance_metrics": [],
        })
        self.assertEqual(ready["messages"][0].content, LANGUAGE_PROMPT)
        self.assertEqual(ready["visitor_welcome_program"]["status"], "awaiting_language")

        language = visitor_onboarding_node({
            **ready, "messages": [HumanMessage(content="English")],
        })
        self.assertEqual(language["messages"][0].content, MODE_PROMPT)
        self.assertEqual(language["visitor_profile"]["language"], "en")
        self.assertEqual(language["visitor_welcome_program"]["status"], "awaiting_mode")

        mode = visitor_onboarding_node({
            **language, "messages": [HumanMessage(content="Classic Mode")],
        })
        self.assertEqual(mode["visitor_welcome_program"]["status"], "completed")
        self.assertEqual(mode["journey_mode_selection"]["selected_mode"], "classic")
        self.assertEqual(route_after_visitor_onboarding(mode), "profile_collection")

    def test_chinese_ready_and_free_text_language_are_supported(self):
        ready = visitor_onboarding_node({
            "messages": [HumanMessage(content="我准备好了")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_ready",
            },
            "performance_metrics": [],
        })
        language = visitor_onboarding_node({
            **ready, "messages": [HumanMessage(content="泰语")],
        })
        self.assertEqual(language["visitor_profile"]["language"], "泰语")
        mode = visitor_onboarding_node({
            **language, "messages": [HumanMessage(content="定制模式")],
        })
        self.assertEqual(mode["journey_mode_selection"]["selected_mode"], "custom")
        self.assertIn("language", mode["profile_collection"]["resolved_fields"])
        self.assertEqual(mode["profile_collection"]["next_missing_field"], "available_minutes")

    def test_active_onboarding_has_priority_over_global_route_fallbacks(self):
        state = {
            "messages": [HumanMessage(content="准备好了")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_ready",
            },
        }
        self.assertEqual(route_initial_request(state), "visitor_onboarding")

    def test_existing_thread_is_migrated_without_replaying_welcome(self):
        result = visitor_welcome_node({
            "messages": [
                HumanMessage(content="继续"),
                AIMessage(content="已有会话回复"),
            ],
            "tour_state": {"route_status": "touring"},
        })
        self.assertNotIn("messages", result)
        self.assertEqual(result["visitor_welcome_program"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
