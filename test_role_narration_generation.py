from __future__ import annotations

import json
import unittest

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import compile_style_brief
from narration_validation import validate_role_narration
from role_narration_generation import generate_role_narration


class RoleNarrationGenerationTests(unittest.TestCase):
    def plan(self, style_id="ancient_scholar"):
        return NarrationContentPlan(
            stop_id="front", style_id=style_id, language="zh", budget_seconds=60,
            facts=(NarrationFact("craft:灰塑", "craft_background", "屋脊可见灰塑。"),),
            must_include=("approved_observation_detail",), already_covered=(),
            must_not_claim=("unreviewed_date",), interaction_allowed=style_id != "listen_only",
        )

    @staticmethod
    def response(style_id, public_text, used=None):
        return json.dumps({
            "schema_version": "role_narration_candidate_v1",
            "style_id": style_id,
            "public_text": public_text,
            "used_fact_ids": used if used is not None else ["craft:灰塑"],
            "omitted_fact_ids": [],
            "self_check": {"added_new_facts": False, "role_consistent": True, "within_budget": True},
        }, ensure_ascii=False)

    def test_valid_role_wrapper_preserves_atomic_fact(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "诸位且看，屋脊可见灰塑。可从容细观。"))
        result = validate_role_narration(value, plan, brief)
        self.assertEqual(result.validation_status, "accepted")
        self.assertEqual(result.state_writes, ())

    def test_new_story_or_date_is_rejected_even_if_self_check_claims_safe(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。传说它创作于1888年。"))
        result = validate_role_narration(value, plan, brief)
        self.assertEqual(result.validation_status, "rejected")
        self.assertIn("unapproved_fact_trigger", result.reason_codes)

    def test_unapproved_fact_id_and_internal_fields_are_rejected(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。 source_ids=S1", ["fact:unknown"]))
        result = validate_role_narration(value, plan, brief)
        self.assertIn("fact_id_boundary_violation", result.reason_codes)
        self.assertIn("internal_field_leak", result.reason_codes)

    def test_listen_only_forbids_questions_and_tasks(self):
        plan = self.plan("listen_only")
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。请你拍照好吗？"))
        result = validate_role_narration(value, plan, brief)
        self.assertIn("listen_only_interaction_violation", result.reason_codes)

    def test_model_failure_returns_auditable_rejection(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(value.generation_status, "rejected")
        self.assertTrue(value.model_called)

    def test_invalid_first_schema_gets_one_bounded_repair(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        outputs = iter([
            '{"unexpected":true}',
            self.response(plan.style_id, "诸位且看，屋脊可见灰塑。"),
        ])
        value = generate_role_narration(plan, brief, lambda _: next(outputs))
        self.assertEqual(value.generation_status, "generated")
        self.assertEqual(value.used_fact_ids, ("craft:灰塑",))


if __name__ == "__main__":
    unittest.main()
