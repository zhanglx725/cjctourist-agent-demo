"""Offline C6 policy tests; no Agent, RAG, route or narration integration."""

from __future__ import annotations

from copy import deepcopy
import unittest

from guidance_policy import build_guidance_policy
from visitor_profile import VisitorProfileError, create_visitor_profile


class GuidancePolicyTests(unittest.TestCase):
    def test_default_profile_is_neutral_and_stable(self):
        profile = create_visitor_profile()
        first = build_guidance_policy(profile)
        second = build_guidance_policy(profile)
        self.assertEqual(first, second)
        self.assertEqual(first.max_items_per_stop, 2)
        self.assertEqual(first.vocabulary_level, "general")
        self.assertFalse(first.interaction_task_enabled)
        self.assertTrue(first.fact_evidence_required)
        self.assertEqual(first.budget_cap_mode, "min_with_stop_budget")

    def test_child_story_interactive_policy_uses_simple_language_and_tasks(self):
        policy = build_guidance_policy(create_visitor_profile(
            audience_mode="child_friendly", explanation_style="story", interaction_mode="interactive_tasks"
        ))
        self.assertEqual(policy.vocabulary_level, "simple")
        self.assertEqual(policy.narrative_mode, "story")
        self.assertTrue(policy.interaction_task_enabled)
        self.assertTrue(policy.proactive_question_enabled)

    def test_child_friendly_normal_mode_keeps_one_observation_task(self):
        policy = build_guidance_policy(create_visitor_profile(audience_mode="child_friendly"))
        self.assertTrue(policy.interaction_task_enabled)
        self.assertFalse(policy.proactive_question_enabled)

    def test_family_stays_simple_without_claiming_personal_identity(self):
        policy = build_guidance_policy(create_visitor_profile(audience_mode="family"))
        self.assertEqual(policy.vocabulary_level, "simple")
        self.assertFalse(policy.optional_deepening_enabled)

    def test_study_and_mixed_group_keep_optional_deepening_boundaries(self):
        study = build_guidance_policy(create_visitor_profile(audience_mode="study", knowledge_level="enthusiast"))
        mixed = build_guidance_policy(create_visitor_profile(audience_mode="mixed_group", knowledge_level="general"))
        self.assertEqual(study.vocabulary_level, "general")
        self.assertTrue(study.optional_deepening_enabled)
        self.assertEqual(mixed.vocabulary_level, "simple")
        self.assertTrue(mixed.optional_deepening_enabled)

    def test_professional_short_does_not_become_deep(self):
        policy = build_guidance_policy(create_visitor_profile(
            detail_level="short", knowledge_level="professional", explanation_style="technical"
        ))
        self.assertEqual(policy.max_items_per_stop, 1)
        self.assertEqual(policy.explanation_length, "short")
        self.assertEqual(policy.expansion_depth, "minimal")
        self.assertEqual(policy.citation_detail, "detailed")
        self.assertEqual(policy.narrative_mode, "technical")

    def test_listen_only_overrides_interactive_style(self):
        policy = build_guidance_policy(create_visitor_profile(
            explanation_style="interactive", interaction_mode="listen_only"
        ))
        self.assertEqual(policy.narrative_mode, "interactive")
        self.assertFalse(policy.interaction_task_enabled)
        self.assertFalse(policy.proactive_question_enabled)

    def test_deep_only_enables_future_card_interfaces_without_loading_cards(self):
        standard = build_guidance_policy(create_visitor_profile(detail_level="standard"))
        deep = build_guidance_policy(create_visitor_profile(detail_level="deep"))
        self.assertFalse(standard.comparison_enabled)
        self.assertFalse(standard.research_extension_enabled)
        self.assertTrue(deep.comparison_enabled)
        self.assertTrue(deep.research_extension_enabled)

    def test_dict_input_is_validated_and_input_is_not_mutated(self):
        serialized = {
            "available_minutes": 30, "interests": ["灰塑"], "detail_level": "standard",
            "audience_mode": "child_friendly", "knowledge_level": "general",
            "explanation_style": "story", "interaction_mode": "normal",
        }
        original = deepcopy(serialized)
        policy = build_guidance_policy(serialized)
        self.assertEqual(serialized, original)
        self.assertEqual(policy.vocabulary_level, "simple")
        with self.assertRaises(VisitorProfileError):
            build_guidance_policy({**serialized, "audience_mode": "unknown"})


if __name__ == "__main__":
    unittest.main()
