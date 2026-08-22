"""Scene-specific validation entry points must not accept another scene."""

from __future__ import annotations

import unittest

from narration_content_plan import NarrationContentPlan
from narration_style_policy import compile_style_brief
from narration_validation import (
    validate_qa_role_narration,
    validate_stop_guidance_role_narration,
)
from presentation_content_plan import build_presentation_content_plan
from route_role_narration_shadow import (
    build_route_role_text_candidate,
    validate_closing_role_narration,
    validate_navigation_role_narration,
    validate_replan_presentation,
)


class ProductSceneValidatorTests(unittest.TestCase):
    def test_stop_and_qa_contracts_reject_each_others_plans(self):
        brief = compile_style_brief("ancient_scholar")
        stop_plan = NarrationContentPlan(
            stop_id="front_hall", style_id="ancient_scholar", language="zh",
            budget_seconds=30, facts=(), must_include=(), already_covered=(),
            must_not_claim=(), interaction_allowed=True,
        )
        qa_plan = NarrationContentPlan(
            stop_id="qa:tour_qa", style_id="ancient_scholar", language="zh",
            budget_seconds=30, facts=(), must_include=(), already_covered=(),
            must_not_claim=(), interaction_allowed=True,
        )
        self.assertEqual(
            validate_stop_guidance_role_narration(None, qa_plan, brief).reason_codes,
            ("stop_guidance_plan_required",),
        )
        self.assertEqual(
            validate_qa_role_narration(None, stop_plan, brief).reason_codes,
            ("qa_plan_required",),
        )

    def test_navigation_and_closing_contracts_reject_cross_scene_candidates(self):
        legacy = "按既定路线继续前往下一站。"
        navigation_plan = build_presentation_content_plan(
            scene_kind="navigation", role_mode="ancient_scholar",
            detail_level="standard", budget_seconds=120,
            source_of_facts=("tour_state", "approved_spatial_graph", "route_stop_catalog"),
        )
        candidate = build_route_role_text_candidate(
            scene_kind="navigation", role_mode="ancient_scholar",
            legacy_text=legacy,
        )
        self.assertEqual(
            validate_navigation_role_narration(
                candidate, plan=navigation_plan, legacy_text=legacy,
            )["validation_status"],
            "accepted",
        )
        closing = validate_closing_role_narration(
            candidate, plan=navigation_plan, legacy_text=legacy,
        )
        self.assertEqual(closing["validation_status"], "rejected")
        self.assertIn("tour_closing_plan_required", closing["reason_codes"])

    def test_replan_contract_preserves_authoritative_text_and_has_no_state_writes(self):
        legacy = "是否将剩余路线调整为精简路线？"
        accepted = validate_replan_presentation(legacy, legacy_text=legacy)
        rejected = validate_replan_presentation("直接改成精简路线。", legacy_text=legacy)
        self.assertEqual(accepted["validation_status"], "accepted")
        self.assertEqual(accepted["state_writes"], [])
        self.assertEqual(rejected["validation_status"], "rejected")
        self.assertIn("legacy_replan_boundary_changed", rejected["reason_codes"])


if __name__ == "__main__":
    unittest.main()
