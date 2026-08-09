from __future__ import annotations

import json
import unittest

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import compile_style_brief
from narration_validation import validate_role_narration
from role_narration_generation import (
    generate_role_narration,
    role_narration_prompt,
    role_narration_candidate_from_dict,
    validate_candidate_shape,
)


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

    def test_opaque_fact_token_is_hydrated_before_validation(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "请看，[[FACT_000]]可以从容细观。"),
        )
        self.assertNotIn("[[FACT_000]]", value.public_text)
        self.assertIn(plan.facts[0].statement, value.public_text)
        self.assertEqual(
            validate_role_narration(value, plan, brief).validation_status,
            "accepted",
        )

    def test_missing_or_unknown_fact_placeholder_fails_closed(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        for public_text in ("这里只做角色表达。", "[[FACT_999]]"):
            with self.subTest(public_text=public_text):
                value = generate_role_narration(
                    plan, brief,
                    lambda _: self.response(plan.style_id, public_text),
                )
                self.assertEqual(value.generation_status, "rejected")
                self.assertEqual(value.reason_code, "invalid_fact_placeholders")

    def test_prompt_keeps_all_facts_but_omits_non_expression_plan_fields(self):
        plan = self.plan()
        prompt = role_narration_prompt(plan, compile_style_brief(plan.style_id))
        self.assertIn(plan.facts[0].statement, prompt)
        self.assertIn('"interaction_allowed":true', prompt)
        self.assertIn('"must_include":', prompt)
        self.assertNotIn('"stop_id":', prompt)
        self.assertNotIn('"already_covered":', prompt)

    def test_prompt_example_uses_every_required_fact_and_connector_budget(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh", budget_seconds=60,
            facts=(
                NarrationFact("fact:a", "craft_background", "审核事实甲。"),
                NarrationFact("fact:b", "object_detail", "审核事实乙。"),
            ),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True,
        )
        prompt = role_narration_prompt(plan, compile_style_brief("neutral"))
        self.assertIn('"public_text":"[[FACT_000]][[FACT_001]]"', prompt)
        self.assertIn('"used_fact_ids":["fact:a","fact:b"]', prompt)
        self.assertIn('"omitted_fact_ids":[]', prompt)
        self.assertIn('"max_role_connector_characters":', prompt)

    def test_infeasible_required_fact_budget_fails_before_model_call(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh", budget_seconds=1,
            facts=(NarrationFact("fact:a", "craft_background", "这是一条明显超过四个字的审核事实。"),),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True,
        )
        calls = []
        value = generate_role_narration(
            plan, compile_style_brief("neutral"), lambda prompt: calls.append(prompt),
        )
        self.assertEqual(value.reason_code, "fact_budget_infeasible")
        self.assertFalse(value.model_called)
        self.assertEqual(calls, [])

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
        self.assertIn("invalid_fact_placeholders", result.reason_codes)

    def test_internal_field_leak_is_rejected_after_fact_hydration(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "[[FACT_000]]source_ids=S1"),
        )
        result = validate_role_narration(value, plan, brief)
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

    def test_wire_schema_rejects_missing_extra_wrong_type_enum_and_version(self):
        plan = self.plan()
        valid = json.loads(self.response(plan.style_id, "屋脊可见灰塑。"))
        cases = []
        missing = dict(valid)
        missing.pop("self_check")
        cases.append(missing)
        extra = dict(valid)
        extra["node_id"] = "front_courtyard"
        cases.append(extra)
        wrong_type = dict(valid)
        wrong_type["used_fact_ids"] = "craft:灰塑"
        cases.append(wrong_type)
        unknown_enum = dict(valid)
        unknown_enum["style_id"] = "made_up_role"
        cases.append(unknown_enum)
        unknown_version = dict(valid)
        unknown_version["schema_version"] = "role_narration_candidate_v99"
        cases.append(unknown_version)
        for value in cases:
            result = validate_candidate_shape(
                value, expected_style_id=plan.style_id, latency_ms=1,
            )
            self.assertEqual(result.generation_status, "rejected")
            self.assertIn(result.reason_code, {"invalid_candidate_schema", "invalid_candidate_fields"})

    def test_internal_envelope_is_strict_and_does_not_accept_unknown_fields(self):
        plan = self.plan()
        candidate = generate_role_narration(
            plan, compile_style_brief(plan.style_id),
            lambda _: self.response(plan.style_id, "屋脊可见灰塑。"),
        ).to_dict()
        self.assertIsNotNone(role_narration_candidate_from_dict(candidate))
        candidate["state_patch"] = {"tour_state": {"current_stop_id": "front"}}
        self.assertIsNone(role_narration_candidate_from_dict(candidate))

    def test_model_candidate_cannot_contain_internal_or_final_answer_fields(self):
        plan = self.plan()
        for field, value in (
            ("source_ids", ["S01"]),
            ("node_id", "front_courtyard"),
            ("tour_state", {"current_stop_id": "front"}),
            ("visitor_profile", {"language": "zh"}),
            ("final_visitor_answer", "请确认完成本点。"),
        ):
            value_to_check = json.loads(self.response(plan.style_id, "屋脊可见灰塑。"))
            value_to_check[field] = value
            result = validate_candidate_shape(
                value_to_check, expected_style_id=plan.style_id, latency_ms=1,
            )
            self.assertEqual(result.generation_status, "rejected")
            self.assertEqual(result.reason_code, "invalid_candidate_schema")


if __name__ == "__main__":
    unittest.main()
