from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import (
    route_after_atomic_read_plan_shadow,
    route_after_visitor_onboarding,
    route_after_visitor_welcome,
    route_initial_request,
    visitor_onboarding_node,
    visitor_onboarding_resume_node,
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

    def test_first_mode_request_skips_ready_but_preserves_missing_language(self):
        result = visitor_welcome_node({
            "messages": [HumanMessage(content="选择经典模式，安排30分钟路线")],
            "performance_metrics": [],
        })
        self.assertEqual(result["messages"][0].content, WELCOME_MESSAGE)
        self.assertEqual(result["visitor_welcome_program"]["status"], "awaiting_ready")
        combined = {
            **result,
            "messages": [HumanMessage(content="选择经典模式，安排30分钟路线")],
        }
        onboarding = visitor_onboarding_node(combined)
        self.assertEqual(onboarding["visitor_welcome_program"]["status"], "awaiting_language")
        self.assertEqual(onboarding["visitor_welcome_program"]["selected_mode"], "classic")
        self.assertEqual(onboarding["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(onboarding["messages"][0].content, LANGUAGE_PROMPT)

    def test_preferences_before_mode_are_saved_and_only_missing_slots_are_asked(self):
        preferences = visitor_onboarding_node({
            "messages": [HumanMessage(content="我喜欢灰塑和木雕，选择故事风格")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_ready",
            },
            "performance_metrics": [],
        })
        self.assertEqual(preferences["visitor_profile"]["interests"], ["灰塑", "木雕"])
        self.assertEqual(preferences["visitor_profile"]["explanation_style"], "story")
        self.assertEqual(preferences["visitor_welcome_program"]["status"], "awaiting_language")

        language = visitor_onboarding_node({
            **preferences, "messages": [HumanMessage(content="English")],
        })
        self.assertEqual(language["visitor_welcome_program"]["status"], "awaiting_mode")

        mode = visitor_onboarding_node({
            **language, "messages": [HumanMessage(content="Custom Mode")],
        })
        collection = mode["profile_collection"]
        self.assertEqual(collection["next_missing_field"], "available_minutes")
        self.assertCountEqual(
            collection["resolved_fields"],
            ["interests", "explanation_style", "language"],
        )

    def test_all_slots_in_one_turn_can_start_custom_route_without_reasking(self):
        state = {
            "messages": [HumanMessage(content=(
                "选择定制模式，使用中文，安排60分钟路线，"
                "我喜欢灰塑和木雕，选择故事风格"
            ))],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_ready",
            },
            "performance_metrics": [],
        }
        result = visitor_onboarding_node(state)
        self.assertEqual(result["visitor_welcome_program"]["status"], "completed")
        self.assertEqual(result["profile_collection"]["status"], "ready")
        self.assertIsNone(result["profile_collection"]["next_missing_field"])
        self.assertEqual(route_after_visitor_onboarding(result), "direct_route")

    def test_first_fact_question_preserves_onboarding_and_routes_to_qa(self):
        first = visitor_welcome_node({
            "messages": [HumanMessage(content="陈家祠是哪年建立的")],
            "performance_metrics": [],
        })
        self.assertEqual(first["visitor_welcome_program"]["status"], "awaiting_ready")
        routed_state = {
            **first,
            "messages": [HumanMessage(content="陈家祠是哪年建立的")],
        }
        self.assertIn(route_initial_request(routed_state), {"direct_rag", "tour_qa"})

    def test_question_answer_resumes_exact_unanswered_onboarding_prompt(self):
        prompts = {
            "awaiting_ready": "准备好",
            "awaiting_language": "讲解语言",
            "awaiting_mode": "经典模式",
        }
        for status, expected in prompts.items():
            with self.subTest(status=status):
                state = {
                    "messages": [AIMessage(
                        content="陈氏书院始建于清光绪十四年。",
                        additional_kwargs={"tour_qa_answer": True},
                    )],
                    "visitor_welcome_program": {
                        "schema_version": "visitor_welcome_v1", "status": status,
                    },
                    "performance_metrics": [],
                }
                self.assertEqual(
                    route_after_atomic_read_plan_shadow(state),
                    "visitor_onboarding_resume",
                )
                resumed = visitor_onboarding_resume_node(state)
                self.assertIn(expected, resumed["messages"][0].content)
                self.assertNotIn("visitor_welcome_program", resumed)

        profile_state = {
            "messages": [AIMessage(
                content="陈氏书院始建于清光绪十四年。",
                additional_kwargs={"tour_qa_answer": True},
            )],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "completed",
            },
            "profile_collection": {
                "status": "collecting", "next_missing_field": "interests",
            },
            "performance_metrics": [],
        }
        self.assertEqual(
            route_after_atomic_read_plan_shadow(profile_state),
            "visitor_onboarding_resume",
        )
        resumed_profile = visitor_onboarding_resume_node(profile_state)
        self.assertIn("您更想看什么", resumed_profile["messages"][0].content)
        self.assertNotIn("profile_collection", resumed_profile)

        prompt_state = {
            **profile_state,
            "messages": [AIMessage(
                content="您更想看什么？",
                additional_kwargs={"profile_collection_prompt": True},
            )],
        }
        self.assertEqual(route_after_atomic_read_plan_shadow(prompt_state), "__end__")


if __name__ == "__main__":
    unittest.main()
