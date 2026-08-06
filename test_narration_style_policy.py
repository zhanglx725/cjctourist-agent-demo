import unittest
from narration_style_policy import _load_all, _validate, compile_narration_style, load_narration_style
from guidance_policy import build_guidance_policy
from visitor_profile import create_visitor_profile

EXPECTED_STYLE_IDS = {
    "neutral", "child", "family", "student_research", "professional",
    "listen_only", "mixed_group", "dominant_ceo", "cute_junior",
    "ancient_scholar", "warm_sister", "bestie_chat", "buddy_guide",
    "exploration_game", "photo_guide", "hostel_scholar",
    "xiguan_young_master", "cantonese_storyteller",
}


class NarrationStylePolicyTests(unittest.TestCase):
    def policy(self, **values): return build_guidance_policy(create_visitor_profile(**values))
    def test_all_approved_styles_load(self): self.assertEqual(set(_load_all()), EXPECTED_STYLE_IDS)
    def test_multi_template_style_loads_as_stable_candidates(self):
        templates = load_narration_style("ancient_scholar").templates
        self.assertIsInstance(templates["first_craft_intro_style"], tuple)
        self.assertEqual(len(templates["first_craft_intro_style"]), 5)
    def test_unknown_style_fallback_is_neutral(self): self.assertEqual(load_narration_style("unknown").style_id, "neutral")
    def test_missing_field_fails_closed(self):
        raw = {"schema_version": "narration_style_v1"}
        with self.assertRaises(ValueError): _validate(raw)
    def test_illegal_placeholder_fails_closed(self):
        raw = {"schema_version": "narration_style_v1", "style_id": "x", "display_name": "x", "applicable_policy_conditions": [], "vocabulary_level": "x", "sentence_length": "x", "narrative_pacing": "x", "craft_explanation_style": "x", "ornament_explanation_style": "x", "interaction_patterns": [], "observation_prompt_patterns": [], "allowed_devices": [], "prohibited_patterns": [], "fallback_style_id": "neutral", "templates": {k: "{unknown}" for k in ("first_craft_intro_style", "repeat_craft_style", "first_ornament_intro_style", "repeat_ornament_style")}}
        with self.assertRaises(ValueError): _validate(raw)
    def test_policy_selection_is_deterministic(self):
        p = self.policy(audience_mode="family")
        self.assertEqual(compile_narration_style(p), compile_narration_style(p))
    def test_named_profile_style_is_selected(self):
        for style_id in EXPECTED_STYLE_IDS - {"neutral", "child", "family", "student_research", "professional", "listen_only", "mixed_group"}:
            with self.subTest(style_id=style_id):
                self.assertEqual(compile_narration_style(self.policy(explanation_style=style_id)).style_id, style_id)
    def test_policy_does_not_copy_profile(self):
        style = compile_narration_style(self.policy(interests=["灰塑"], available_minutes=90))
        self.assertFalse(hasattr(style, "interests")); self.assertFalse(hasattr(style, "available_minutes"))
    def test_listen_only_has_no_question_or_task_template(self):
        s = compile_narration_style(self.policy(interaction_mode="listen_only"))
        self.assertTrue(all("？" not in v and "任务" not in v for v in s.templates.values()))
    def test_child_templates_do_not_add_source_or_site_facts(self):
        s = compile_narration_style(self.policy(audience_mode="child_friendly"))
        self.assertTrue(all("陈家祠" not in v and "S" not in v for v in s.templates.values()))
    def test_professional_does_not_carry_source_ids(self):
        s = compile_narration_style(self.policy(knowledge_level="professional"))
        self.assertFalse(hasattr(s, "source_ids"))

if __name__ == "__main__": unittest.main()
