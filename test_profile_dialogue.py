"""Offline C2 tests for controlled visitor-profile collection."""

from __future__ import annotations

import unittest

from profile_dialogue import collect_profile_input


class ProfileDialogueTests(unittest.TestCase):
    def test_complete_route_input_forms_profile_without_follow_up(self):
        result = collect_profile_input(
            None, "我有30分钟，喜欢灰塑和木雕，简单讲讲，帮我规划路线", start_collection=True
        )
        assert result is not None
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.collection.profile.available_minutes, 30)
        self.assertEqual(result.collection.profile.interests, ("木雕", "灰塑"))
        self.assertEqual(result.collection.profile.detail_level, "short")

    def test_missing_fields_are_prompted_in_frozen_order(self):
        first = collect_profile_input(None, "帮我规划路线", start_collection=True)
        assert first is not None
        self.assertEqual(first.collection.next_missing_field, "available_minutes")
        self.assertIn("多少分钟", first.message)
        second = collect_profile_input(first.collection.to_dict(), "半小时")
        assert second is not None
        self.assertEqual(second.collection.next_missing_field, "interests")
        third = collect_profile_input(second.collection.to_dict(), "都可以")
        assert third is not None
        self.assertEqual(third.collection.profile.interests, ())
        self.assertEqual(third.collection.next_missing_field, "detail_level")
        fourth = collect_profile_input(third.collection.to_dict(), "想深入学习")
        assert fourth is not None
        self.assertEqual(fourth.status, "ready")
        self.assertEqual(fourth.collection.profile.detail_level, "deep")

    def test_minimize_walking_persists_without_becoming_a_required_question(self):
        first = collect_profile_input(
            None, "帮我规划一条少走路的路线", start_collection=True
        )
        assert first is not None
        self.assertEqual(first.collection.next_missing_field, "available_minutes")
        self.assertEqual(
            first.collection.profile.route_constraint, "minimize_walking"
        )
        second = collect_profile_input(first.collection.to_dict(), "30分钟")
        assert second is not None
        self.assertEqual(
            second.collection.profile.route_constraint, "minimize_walking"
        )
        third = collect_profile_input(second.collection.to_dict(), "都可以")
        assert third is not None
        fourth = collect_profile_input(third.collection.to_dict(), "标准讲解")
        assert fourth is not None
        self.assertEqual(fourth.status, "ready")
        self.assertEqual(
            fourth.collection.profile.route_constraint, "minimize_walking"
        )
        self.assertIn("优先减少预计步行", fourth.message)

    def test_neutral_time_uses_explicit_default_without_guessing_interests(self):
        first = collect_profile_input(None, "规划路线", start_collection=True)
        assert first is not None
        second = collect_profile_input(first.collection.to_dict(), "不确定")
        assert second is not None
        self.assertEqual(second.collection.profile.available_minutes, 60)
        self.assertEqual(second.collection.next_missing_field, "interests")

    def test_conflicts_and_invalid_time_do_not_partially_update(self):
        initial = collect_profile_input(None, "规划路线", start_collection=True)
        assert initial is not None
        conflict = collect_profile_input(initial.collection.to_dict(), "我有30分钟或60分钟")
        assert conflict is not None
        self.assertEqual(conflict.status, "clarification")
        self.assertEqual(conflict.collection.to_dict(), initial.collection.to_dict())
        invalid = collect_profile_input(initial.collection.to_dict(), "我有150分钟")
        assert invalid is not None
        self.assertEqual(invalid.status, "clarification")
        self.assertEqual(invalid.collection.to_dict(), initial.collection.to_dict())

    def test_rag_questions_and_non_profile_text_are_not_collected(self):
        self.assertIsNone(collect_profile_input(None, "灰塑是什么？"))
        active = collect_profile_input(None, "规划路线", start_collection=True)
        assert active is not None
        self.assertIsNone(collect_profile_input(active.collection.to_dict(), "这里的灰塑有什么特点？"))

    def test_c5_preferences_remain_neutral_defaults_and_are_never_inferred(self):
        result = collect_profile_input(None, "我有30分钟，喜欢灰塑，标准讲解，规划路线", start_collection=True)
        assert result is not None
        self.assertEqual(result.status, "ready")
        saved = result.collection.profile.to_dict()
        self.assertEqual(saved["audience_mode"], "standard")
        self.assertEqual(saved["knowledge_level"], "general")
        self.assertEqual(saved["explanation_style"], "standard")
        self.assertEqual(saved["interaction_mode"], "normal")
        for field in ("visitor_type", "language", "photo_preference", "accessibility_need"):
            self.assertNotIn(field, saved)


if __name__ == "__main__":
    unittest.main()
