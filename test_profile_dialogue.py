"""Offline C2 tests for controlled visitor-profile collection."""

from __future__ import annotations

import unittest

from profile_dialogue import STYLE_SELECTION_PROMPT, collect_profile_input, extract_profile_patch


class ProfileDialogueTests(unittest.TestCase):
    def test_interests_preserve_the_visitors_mention_order(self) -> None:
        result = collect_profile_input(
            None, "我喜欢灰塑和木雕", start_collection=True,
        )
        self.assertEqual(result.collection.profile.interests, ("灰塑", "木雕"))
    def test_style_prompt_lists_all_eighteen_reviewed_yaml_styles(self):
        expected = (
            "中性清晰", "儿童友好", "亲子共游", "研学观察", "专业讲解", "静听模式", "混合群体",
            "霸道总裁", "奶气学弟", "古风书生", "知心姐姐", "闺蜜唠嗑", "兄弟搭子",
            "探秘闯关", "打卡出片", "祠中宿生", "西关少爷（粤语）", "粤派讲古（粤语）",
        )
        self.assertIn("18种可选风格", STYLE_SELECTION_PROMPT)
        for display_name in expected:
            with self.subTest(display_name=display_name):
                self.assertEqual(STYLE_SELECTION_PROMPT.count(display_name), 1)
        for invented_name in ("金牌导游", "故事派", "工艺派", "寻宝派"):
            self.assertNotIn(invented_name, STYLE_SELECTION_PROMPT)

    def test_complete_route_input_forms_profile_without_follow_up(self):
        result = collect_profile_input(
            None, "我有30分钟，喜欢灰塑和木雕，简单讲讲，帮我规划路线", start_collection=True
        )
        assert result is not None
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.collection.profile.available_minutes, 30)
        self.assertEqual(result.collection.profile.interests, ("灰塑", "木雕"))
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

    def test_explicit_english_deep_phrases_are_collected_deterministically(self):
        for text in ("30 minutes, deep explanation", "one hour, detailed tour"):
            with self.subTest(text=text):
                result = collect_profile_input(None, text, start_collection=True)
                assert result is not None
                self.assertEqual(result.collection.profile.detail_level, "deep")

    def test_bare_number_is_minutes_only_in_the_active_time_slot(self):
        first = collect_profile_input(None, "帮我规划路线", start_collection=True)
        second = collect_profile_input(first.collection.to_dict(), "45")
        self.assertEqual(second.collection.profile.available_minutes, 45)
        self.assertIn("available_minutes", second.collection.resolved_fields)
        self.assertNotEqual(second.collection.next_missing_field, "available_minutes")
        self.assertIsNone(collect_profile_input(None, "45", start_collection=False))

    def test_natural_listen_only_expression_sets_style_and_interaction_mode(self):
        result = collect_profile_input(
            None, "我只想安静听讲，不需要互动", start_collection=True,
            required_fields=("explanation_style",),
        )
        self.assertEqual(result.collection.profile.explanation_style, "listen_only")
        self.assertEqual(result.collection.profile.interaction_mode, "listen_only")

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

    def test_new_approved_style_names_are_parsed_without_polluting_interests(self):
        cases = {
            "我想要霸道总裁讲解风格": "dominant_ceo",
            "选择古风书生风格": "ancient_scholar",
            "用探秘闯关风格讲解": "exploration_game",
            "我喜欢打卡出片风格": "photo_guide",
            "请用粤派讲古风格": "cantonese_storyteller",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                patch, fields, issue = extract_profile_patch(text)
                self.assertIsNone(issue)
                self.assertEqual(patch.get("explanation_style"), expected)
                self.assertIn("explanation_style", fields)
                self.assertNotIn("interests", patch)

    def test_all_display_names_resolve_when_the_style_question_is_active(self):
        cases = {
            "中性清晰": "neutral", "儿童友好": "child", "亲子共游": "family",
            "研学观察": "student_research", "专业讲解": "professional",
            "静听模式": "listen_only", "混合群体": "mixed_group",
            "霸道总裁": "dominant_ceo", "奶气学弟": "cute_junior",
            "古风书生": "ancient_scholar", "知心姐姐": "warm_sister",
            "闺蜜唠嗑": "bestie_chat", "兄弟搭子": "buddy_guide",
            "探秘闯关": "exploration_game", "打卡出片": "photo_guide",
            "祠中宿生": "hostel_scholar", "西关少爷": "xiguan_young_master",
            "粤派讲古": "cantonese_storyteller",
        }
        for display_name, style_id in cases.items():
            with self.subTest(display_name=display_name):
                result = collect_profile_input(
                    None, display_name, start_collection=True,
                    required_fields=("explanation_style",),
                )
                assert result is not None
                self.assertEqual(result.status, "ready")
                self.assertEqual(result.collection.profile.explanation_style, style_id)

    def test_new_style_conflict_requires_clarification(self):
        patch, fields, issue = extract_profile_patch("选择古风书生风格和打卡出片风格")
        self.assertEqual(patch, {})
        self.assertEqual(fields, set())
        self.assertIn("多个不同选择", issue or "")


if __name__ == "__main__":
    unittest.main()
