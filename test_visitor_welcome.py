from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import (
    route_after_atomic_read_plan_shadow,
    route_after_visitor_localization,
    route_after_visitor_onboarding,
    route_after_visitor_welcome,
    route_initial_request,
    visitor_onboarding_node,
    visitor_onboarding_resume_node,
    visitor_localization_node,
    visitor_welcome_node,
)
from visitor_welcome import (
    LANGUAGE_PROMPT,
    LANGUAGE_REQUIRED_PROMPT,
    MODE_PROMPT,
    WELCOME_MESSAGE,
)


class VisitorWelcomeTests(unittest.TestCase):
    @patch("agent_graph._invoke_visitor_translation", return_value="Please choose Classic Mode or Custom Mode.")
    def test_localization_node_replaces_only_public_message(self, translate):
        source = AIMessage(content="请选择经典模式或定制模式。", id="public-message-1")
        result = visitor_localization_node({
            "messages": [source],
            "visitor_profile": {"language": "en"},
            "visitor_localization_audits": [],
            "performance_metrics": [],
            "tour_state": {"route_status": "touring"},
        })
        translate.assert_called_once()
        self.assertEqual(result["messages"][0].id, "public-message-1")
        self.assertEqual(result["messages"][0].content, "Please choose Classic Mode or Custom Mode.")
        self.assertEqual(result["visitor_localization_audits"][-1]["state_writes"], [])
        self.assertNotIn("tour_state", result)

    @patch("agent_graph._invoke_visitor_translation")
    def test_known_pre_language_prompt_stays_bilingual_without_api(self, translate):
        source = AIMessage(content=LANGUAGE_REQUIRED_PROMPT, id="language-prompt-1")
        result = visitor_localization_node({
            "messages": [source], "performance_metrics": [],
        })
        translate.assert_not_called()
        self.assertNotIn("messages", result)
        self.assertEqual(
            result["visitor_localization_audits"][-1]["status"],
            "already_bilingual",
        )

    def test_new_thread_receives_exact_bilingual_welcome_once(self):
        first = visitor_welcome_node({"performance_metrics": []})
        self.assertEqual(first["messages"][0].content, WELCOME_MESSAGE)
        self.assertEqual(first["visitor_welcome_program"]["status"], "awaiting_language")
        self.assertEqual(first["visitor_welcome_program"]["play_count"], 1)
        second = visitor_welcome_node(first)
        self.assertNotIn("messages", second)

    def test_empty_bootstrap_ends_after_welcome(self):
        state = {
            "messages": [AIMessage(content=WELCOME_MESSAGE)],
            "visitor_welcome_program": {"schema_version": "visitor_welcome_v1", "status": "awaiting_language"},
        }
        self.assertEqual(route_after_visitor_welcome(state), "__end__")

    def test_first_user_message_continues_after_welcome_without_being_swallowed(self):
        state = {
            "messages": [
                HumanMessage(content="经典模式"),
                AIMessage(content=WELCOME_MESSAGE),
            ],
            "visitor_welcome_program": {"schema_version": "visitor_welcome_v1", "status": "awaiting_language"},
        }
        self.assertEqual(route_after_visitor_welcome(state), "semantic_normalization")

    def test_language_and_classic_mode_complete_onboarding(self):
        invalid = visitor_onboarding_node({
            "messages": [HumanMessage(content="I'm ready")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
            },
            "performance_metrics": [],
        })
        self.assertEqual(invalid["messages"][0].content, LANGUAGE_REQUIRED_PROMPT)
        self.assertEqual(invalid["visitor_welcome_program"]["status"], "awaiting_language")

        language = visitor_onboarding_node({
            **invalid, "messages": [HumanMessage(content="English")],
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

    def test_free_text_language_is_supported_without_readiness_gate(self):
        language = visitor_onboarding_node({
            "messages": [HumanMessage(content="泰语")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
            },
            "performance_metrics": [],
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
            "messages": [HumanMessage(content="经典模式")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
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
        self.assertEqual(result["visitor_welcome_program"]["status"], "awaiting_language")
        combined = {
            **result,
            "messages": [HumanMessage(content="选择经典模式，安排30分钟路线")],
        }
        onboarding = visitor_onboarding_node(combined)
        self.assertEqual(onboarding["visitor_welcome_program"]["status"], "awaiting_language")
        self.assertEqual(onboarding["visitor_welcome_program"]["selected_mode"], "classic")
        self.assertEqual(onboarding["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(onboarding["messages"][0].content, LANGUAGE_REQUIRED_PROMPT)

    def test_language_and_mode_in_one_turn_do_not_reask_mode(self):
        result = visitor_onboarding_node({
            "messages": [HumanMessage(content="英语，经典模式")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
            },
            "performance_metrics": [],
        })
        self.assertEqual(result["visitor_profile"]["language"], "en")
        self.assertEqual(result["journey_mode_selection"]["selected_mode"], "classic")
        self.assertEqual(result["visitor_welcome_program"]["status"], "completed")
        self.assertEqual(result["profile_collection"]["next_missing_field"], "available_minutes")
        self.assertNotEqual(result["messages"][0].content, MODE_PROMPT)

    def test_mode_before_language_is_remembered_without_reasking(self):
        missing = visitor_onboarding_node({
            "messages": [HumanMessage(content="定制模式")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
            },
            "performance_metrics": [],
        })
        self.assertEqual(missing["messages"][0].content, LANGUAGE_REQUIRED_PROMPT)
        self.assertEqual(missing["visitor_welcome_program"]["selected_mode"], "custom")
        completed = visitor_onboarding_node({
            **missing, "messages": [HumanMessage(content="中文")],
        })
        self.assertEqual(completed["visitor_profile"]["language"], "zh")
        self.assertEqual(completed["journey_mode_selection"]["selected_mode"], "custom")
        self.assertEqual(completed["visitor_welcome_program"]["status"], "completed")

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

    def test_language_classic_mode_and_duration_in_one_turn_are_ready(self):
        state = {
            "messages": [HumanMessage(content="中文，经典模式，30分钟")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1",
                "status": "awaiting_language",
            },
            "performance_metrics": [],
        }
        result = visitor_onboarding_node(state)
        self.assertEqual(result["visitor_welcome_program"]["status"], "completed")
        self.assertEqual(result["journey_mode_selection"]["selected_mode"], "classic")
        self.assertEqual(result["visitor_profile"]["language"], "zh")
        self.assertEqual(result["visitor_profile"]["available_minutes"], 30)
        self.assertEqual(result["profile_collection"]["resolved_fields"], [
            "available_minutes", "language",
        ])
        self.assertEqual(result["profile_collection"]["status"], "ready")
        self.assertIsNone(result["profile_collection"]["next_missing_field"])
        self.assertEqual(route_after_visitor_onboarding(result), "direct_route")

    def test_language_then_classic_mode_and_duration_remain_consistent(self):
        language = visitor_onboarding_node({
            "messages": [HumanMessage(content="中文")],
            "visitor_welcome_program": {
                "schema_version": "visitor_welcome_v1", "status": "awaiting_language",
            },
            "performance_metrics": [],
        })
        self.assertEqual(language["visitor_welcome_program"]["status"], "awaiting_mode")
        completed = visitor_onboarding_node({
            **language, "messages": [HumanMessage(content="选择经典模式，我有20分钟")],
        })
        self.assertEqual(completed["visitor_welcome_program"]["status"], "completed")
        self.assertEqual(completed["profile_collection"]["status"], "ready")
        self.assertEqual(completed["visitor_profile"]["available_minutes"], 20)
        self.assertEqual(route_after_visitor_onboarding(completed), "direct_route")

    def test_first_fact_question_preserves_onboarding_and_routes_to_qa(self):
        first = visitor_welcome_node({
            "messages": [HumanMessage(content="陈家祠是哪年建立的")],
            "performance_metrics": [],
        })
        self.assertEqual(first["visitor_welcome_program"]["status"], "awaiting_language")
        routed_state = {
            **first,
            "messages": [HumanMessage(content="陈家祠是哪年建立的")],
        }
        self.assertIn(route_initial_request(routed_state), {"direct_rag", "tour_qa"})

    def test_question_answer_resumes_exact_unanswered_onboarding_prompt(self):
        prompts = {
            "awaiting_ready": "语言",
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
                    "visitor_localization",
                )
                self.assertEqual(
                    route_after_visitor_localization(state),
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
            "visitor_localization",
        )
        self.assertEqual(
            route_after_visitor_localization(profile_state),
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
        self.assertEqual(route_after_atomic_read_plan_shadow(prompt_state), "visitor_localization")
        self.assertEqual(route_after_visitor_localization(prompt_state), "__end__")


if __name__ == "__main__":
    unittest.main()
