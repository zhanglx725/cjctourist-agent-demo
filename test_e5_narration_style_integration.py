"""E5-A5 tests: style changes prose only, never narration facts or state inputs."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from guidance_policy import build_guidance_policy
from narration_rendering import render_guidance_evidence
from test_e5_narration_rendering import NarrationRenderingTests
from visitor_profile import create_visitor_profile


class NarrationStyleIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = NarrationRenderingTests(methodName="test_first_craft_precedes_object_and_is_not_repeated")
        fixture.setUp()
        self.program = fixture.program
        self.bundle = fixture._bundle()

    @staticmethod
    def _policy(**changes):
        return build_guidance_policy(create_visitor_profile(interests=["灰塑"], **changes))

    def _render(self, **changes):
        return render_guidance_evidence(self.program, self.bundle, self._policy(**changes))

    def _assert_fact_equivalent(self, left, right) -> None:
        self.assertEqual(left.rendered_craft_ids, right.rendered_craft_ids)
        self.assertEqual(left.rendered_ornament_ids, right.rendered_ornament_ids)
        self.assertEqual(left.used_source_ids, right.used_source_ids)
        self.assertEqual(left.eligible_coverage_candidates, right.eligible_coverage_candidates)
        self.assertEqual(left.omitted_ornament_ids, right.omitted_ornament_ids)
        self.assertEqual(left.content_budget_seconds, right.content_budget_seconds)
        self.assertEqual(left.allocated_content_seconds, right.allocated_content_seconds)

    def test_policy_maps_to_all_seven_styles_deterministically(self):
        cases = {
            "neutral": {},
            "child": {"audience_mode": "child_friendly"},
            "family": {"audience_mode": "family"},
            "student_research": {"audience_mode": "study"},
            "professional": {"knowledge_level": "professional"},
            "listen_only": {"interaction_mode": "listen_only"},
            "mixed_group": {"audience_mode": "mixed_group"},
        }
        for expected, changes in cases.items():
            with self.subTest(style=expected):
                result = self._render(**changes)
                self.assertEqual(result.style_id, expected)
                self.assertFalse(result.style_fallback_used)
                self.assertEqual(result, self._render(**changes))

    def test_all_styles_preserve_facts_sources_candidates_and_budget(self):
        neutral = self._render()
        variants = [
            self._render(audience_mode="child_friendly"),
            self._render(audience_mode="family"),
            self._render(audience_mode="study"),
            self._render(knowledge_level="professional"),
            self._render(interaction_mode="listen_only"),
            self._render(audience_mode="mixed_group"),
        ]
        for variant in variants:
            self._assert_fact_equivalent(neutral, variant)
        self.assertTrue(any(variant.visitor_message != neutral.visitor_message for variant in variants))

    def test_style_boundaries_for_child_family_mixed_and_listen_only(self):
        child = self._render(audience_mode="child_friendly")
        family = self._render(audience_mode="family")
        mixed = self._render(audience_mode="mixed_group")
        listen_only = self._render(interaction_mode="listen_only")
        self.assertIn("简单", child.visitor_message)
        self.assertIn("一起", family.visitor_message)
        self.assertNotIn("儿童", family.visitor_message)
        self.assertIn("如需", mixed.visitor_message)
        self.assertNotIn("可以试着", listen_only.visitor_message)
        self.assertNotIn("？", listen_only.visitor_message)

    def test_style_loader_failure_uses_original_neutral_renderer_without_fact_drift(self):
        neutral = self._render()
        with patch("narration_rendering.compile_narration_style", side_effect=ValueError("bad schema")):
            fallback = self._render(audience_mode="child_friendly")
        self._assert_fact_equivalent(neutral, fallback)
        self.assertEqual(fallback.style_id, "neutral")
        self.assertTrue(fallback.style_fallback_used)
        self.assertIn("style_library_unavailable", fallback.style_warning_codes)

    def test_inputs_remain_immutable(self):
        before_program = self.program.to_dict()
        before_bundle = self.bundle.to_dict()
        self._render(audience_mode="family")
        self.assertEqual(self.program.to_dict(), before_program)
        self.assertEqual(self.bundle.to_dict(), before_bundle)

    def test_named_multi_template_style_renders_deterministically(self):
        first = self._render(explanation_style="ancient_scholar")
        second = self._render(explanation_style="ancient_scholar")
        self.assertEqual(first.style_id, "ancient_scholar")
        self.assertFalse(first.style_fallback_used)
        self.assertEqual(first.visitor_message, second.visitor_message)
        self._assert_fact_equivalent(self._render(), first)


if __name__ == "__main__":
    unittest.main()
