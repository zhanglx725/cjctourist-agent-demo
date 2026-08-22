from __future__ import annotations

import unittest

from narration_budget import _component_chars
from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import COMPACT_COMPONENT_KEYS, compile_style_brief
from narration_validation import validate_stop_guidance_role_narration
from role_narration_generation import RoleNarrationCandidate, apply_point_narration_scaffold


PILOT_STYLES = ("child", "ancient_scholar", "dominant_ceo")


def _plan(style_id: str, budget: int = 60) -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id="stop_front_courtyard_center",
        style_id=style_id,
        language="zh",
        budget_seconds=budget,
        allocated_content_seconds=30,
        facts=(
            NarrationFact("craft:stucco:001", "craft_detail", "既定工艺事实甲。"),
            NarrationFact("craft:stucco:002", "craft_detail", "既定工艺事实乙。"),
            NarrationFact("ornament:lion:001", "object_detail", "既定对象事实甲。"),
        ),
        must_include=(),
        already_covered=(),
        must_not_claim=(),
        interaction_allowed=True,
        scaffold_mode="compact",
    )


class CompactRoleComponentTests(unittest.TestCase):
    def test_pilot_styles_have_complete_three_choice_reviewed_library(self):
        for style_id in PILOT_STYLES:
            with self.subTest(style_id=style_id):
                components = compile_style_brief(style_id).point_narration_components
                self.assertTrue(COMPACT_COMPONENT_KEYS.issubset(components))
                self.assertTrue(all(
                    len(components[key]) >= 3 for key in COMPACT_COMPONENT_KEYS
                ))
                for key in COMPACT_COMPONENT_KEYS:
                    other_values = {
                        value
                        for other_key, values in components.items()
                        if other_key != key
                        for value in values
                    }
                    self.assertFalse(
                        set(components[key]) & other_values,
                        f"ambiguous component phrase in {style_id}:{key}",
                    )

    def test_compact_scaffold_covers_opening_middle_transition_and_closing(self):
        for style_id in PILOT_STYLES:
            with self.subTest(style_id=style_id):
                plan = _plan(style_id)
                brief = compile_style_brief(style_id)
                candidate = RoleNarrationCandidate(
                    style_id=style_id,
                    public_text="".join(fact.statement for fact in plan.facts),
                    used_fact_ids=tuple(fact.fact_id for fact in plan.facts),
                    omitted_fact_ids=(),
                    self_check={
                        "added_new_facts": False,
                        "role_consistent": True,
                        "within_budget": True,
                    },
                    model_called=False,
                    latency_ms=0,
                )
                rendered = apply_point_narration_scaffold(
                    candidate, plan, brief, compact=True,
                )
                self.assertEqual(rendered.generation_status, "generated")
                self.assertTrue(any(
                    value in rendered.public_text
                    for value in brief.point_narration_components["compact_opening"]
                ))
                self.assertGreaterEqual(sum(
                    value in rendered.public_text
                    for topic in ("craft", "ornament")
                    for value in brief.point_narration_components[f"{topic}_micro_observation"]
                ), 2)
                self.assertTrue(any(
                    value in rendered.public_text
                    for value in brief.point_narration_components["craft_micro_transition"]
                ))
                self.assertTrue(any(
                    value in rendered.public_text
                    for value in brief.point_narration_components["compact_closing"]
                ))
                validation = validate_stop_guidance_role_narration(
                    rendered, plan, brief, compact=True,
                )
                self.assertEqual(
                    validation.validation_status, "accepted", validation.to_dict(),
                )

    def test_budget_preflight_counts_pilot_micro_components(self):
        for style_id in PILOT_STYLES:
            with self.subTest(style_id=style_id):
                plan = _plan(style_id)
                brief = compile_style_brief(style_id)
                connector_chars = _component_chars(
                    brief, plan.facts, compact=True,
                )
                compact_boundary_chars = sum(map(len, (
                    brief.point_narration_components["compact_opening"][0],
                    brief.point_narration_components["compact_closing"][0],
                )))
                self.assertGreater(connector_chars, compact_boundary_chars)


if __name__ == "__main__":
    unittest.main()
