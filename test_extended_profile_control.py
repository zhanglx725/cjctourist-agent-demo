import unittest

from extended_profile_control import apply_extended_profile_control, parse_extended_profile_control
from visitor_profile import create_visitor_profile


class ExtendedProfileControlTests(unittest.TestCase):
    def test_explicit_controls_produce_atomic_patch(self):
        result = apply_extended_profile_control(
            None, "我是建筑专业的，讲得专业一点"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["knowledge_level"], "professional")
        self.assertEqual(result["profile"]["explanation_style"], "expert")
        self.assertEqual(result["policy"]["narrative_mode"], "expert")
        story = apply_extended_profile_control(result["profile"], "用故事方式讲")
        self.assertTrue(story["ok"])
        self.assertEqual(story["profile"]["explanation_style"], "story")

    def test_explicit_audience_and_listen_only(self):
        child = apply_extended_profile_control(None, "给小朋友讲")
        self.assertEqual(child["profile"]["audience_mode"], "child_friendly")
        quiet = apply_extended_profile_control(child["profile"], "不要再问我问题")
        self.assertEqual(quiet["profile"]["interaction_mode"], "listen_only")
        self.assertFalse(quiet["policy"]["interaction_task_enabled"])

    def test_ambiguous_collective_word_does_not_infer_profile(self):
        self.assertEqual(parse_extended_profile_control("我们一起看看吧").kind, "none")

    def test_conflicting_choice_leaves_profile_unchanged(self):
        original = create_visitor_profile(audience_mode="family").to_dict()
        result = apply_extended_profile_control(original, "给小朋友讲，也按亲子方式讲")
        self.assertFalse(result["ok"])
        self.assertEqual(result["profile"], original)

    def test_reset_only_resets_extended_fields(self):
        original = create_visitor_profile(
            available_minutes=30, interests=["灰塑"], detail_level="deep",
            audience_mode="family", knowledge_level="professional", explanation_style="expert",
            interaction_mode="listen_only",
        ).to_dict()
        result = apply_extended_profile_control(original, "恢复标准讲解")
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile"]["available_minutes"], 30)
        self.assertEqual(result["profile"]["detail_level"], "deep")
        self.assertEqual(result["profile"]["audience_mode"], "standard")
        self.assertEqual(result["profile"]["interaction_mode"], "normal")

    def test_delete_and_view_are_session_control_actions(self):
        profile = create_visitor_profile(audience_mode="study").to_dict()
        view = apply_extended_profile_control(profile, "查看当前画像")
        self.assertTrue(view["ok"])
        self.assertFalse(view["changed"])
        deleted = apply_extended_profile_control(profile, "删除本次偏好")
        self.assertTrue(deleted["ok"])
        self.assertIsNone(deleted["profile"])


if __name__ == "__main__":
    unittest.main()
