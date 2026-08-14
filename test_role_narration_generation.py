from __future__ import annotations

import json
import unittest

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import approved_style_ids, compile_style_brief
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
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "[[FACT_000]]"))
        result = validate_role_narration(value, plan, brief)
        self.assertEqual(result.validation_status, "accepted")
        self.assertEqual(result.state_writes, ())

    def test_opaque_fact_token_is_hydrated_before_validation(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "[[FACT_000]]"),
        )
        self.assertNotIn("[[FACT_000]]", value.public_text)
        self.assertIn(plan.facts[0].statement, value.public_text)
        self.assertEqual(
            validate_role_narration(value, plan, brief).validation_status,
            "accepted",
        )

    def test_safe_envelope_is_scaffolded_with_reviewed_style_components(self):
        plan = self.plan("ancient_scholar")
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "[[FACT_000]]"),
        )
        result = validate_role_narration(candidate, plan, brief)
        self.assertEqual(result.validation_status, "accepted")
        self.assertIn(brief.point_narration_components["opening"][0], candidate.public_text)
        self.assertTrue(any(
            closing in candidate.public_text
            for closing in brief.point_narration_components["closing"]
        ))

    def test_style_forbidden_marker_rejects_candidate_connector_only(self):
        plan = self.plan("ancient_scholar")
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "诸位且看，[[FACT_000]]绝绝子。"),
        )
        self.assertEqual(candidate.generation_status, "rejected")
        self.assertEqual(candidate.reason_code, "model_connector_text_forbidden")

    def test_style_interaction_contract_rejects_listen_only_request(self):
        plan = self.plan("listen_only")
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "静静看，[[FACT_000]]请你拍照。"),
        )
        self.assertEqual(candidate.generation_status, "rejected")
        self.assertEqual(candidate.reason_code, "model_connector_text_forbidden")

    def test_malformed_punctuation_and_repeated_role_prose_fail_closed(self):
        plan = self.plan("cute_junior")
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(
                plan.style_id,
                "先看这里吧。。[[FACT_000]]先看这里吧。",
            ),
        )
        self.assertEqual(candidate.generation_status, "rejected")
        self.assertEqual(candidate.reason_code, "model_connector_text_forbidden")

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

    def test_prompt_includes_executable_style_acceptance_contract(self):
        prompt = role_narration_prompt(
            self.plan("ancient_scholar"),
            compile_style_brief("ancient_scholar"),
        )
        self.assertIn('"acceptance_profile":', prompt)
        self.assertIn('"required_markers":["诸位","且看","可见"]', prompt)
        self.assertIn('"point_narration_strategy":', prompt)
        self.assertIn("审核表达合同", prompt)
        self.assertIn("不得使用 forbidden_markers", prompt)

    def test_prompt_makes_listen_only_contract_explicit(self):
        prompt = role_narration_prompt(
            self.plan("listen_only"), compile_style_brief("listen_only"),
        )
        self.assertIn('"interaction_contract":{"mode":"none","max_requests":0}', prompt)
        self.assertIn("interaction_contract.mode=none", prompt)

    def test_prompt_assigns_all_persona_prose_to_the_deterministic_scaffold(self):
        prompt = role_narration_prompt(
            self.plan("cute_junior"), compile_style_brief("cute_junior"),
        )
        self.assertIn("最终令牌协议", prompt)
        self.assertIn("public_text 必须且只能由已给出的 public_text_token 连续组成", prompt)

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
            interaction_allowed=True, allocated_content_seconds=2,
        )
        calls = []
        value = generate_role_narration(
            plan, compile_style_brief("neutral"), lambda prompt: calls.append(prompt),
        )
        self.assertEqual(value.reason_code, "fact_budget_infeasible")
        self.assertFalse(value.model_called)
        self.assertEqual(calls, [])

    def test_e5_allocated_duration_prevents_double_charging_approved_facts(self):
        statement = "这是已经通过上游审核并分配讲解时长的事实内容。" * 12
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh", budget_seconds=60,
            facts=(NarrationFact("fact:a", "craft_background", statement),),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True, allocated_content_seconds=50,
        )
        candidate = generate_role_narration(
            plan, compile_style_brief("neutral"),
            lambda _: self.response(
                "neutral", "[[FACT_000]]", ["fact:a"],
            ),
        )
        result = validate_role_narration(
            candidate, plan, compile_style_brief("neutral"),
        )
        self.assertEqual(candidate.generation_status, "generated")
        self.assertEqual(result.validation_status, "accepted")
        self.assertTrue(result.within_budget)

    def test_rejected_empty_candidate_is_not_reported_within_budget(self):
        plan = self.plan("neutral")
        candidate = generate_role_narration(
            plan, compile_style_brief("neutral"),
            lambda _: (_ for _ in ()).throw(TimeoutError()),
        )
        result = validate_role_narration(
            candidate, plan, compile_style_brief("neutral"),
        )
        self.assertFalse(result.within_budget)

    def test_incomplete_fact_partition_fails_closed_without_second_model_call(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh", budget_seconds=60,
            facts=(
                NarrationFact("fact:a", "craft_background", "审核事实甲。"),
                NarrationFact("fact:b", "object_detail", "审核事实乙。"),
            ),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True,
        )
        calls = []
        candidate = generate_role_narration(
            plan, compile_style_brief("neutral"),
            lambda _: (calls.append(1) or self.response("neutral", "[[FACT_000]]", ["fact:a"])),
        )
        self.assertEqual(candidate.generation_status, "rejected")
        self.assertEqual(candidate.reason_code, "invalid_fact_id_partition")
        self.assertEqual(calls, [1])

    def test_overlong_connectors_fail_closed_without_second_model_call(self):
        plan = self.plan("neutral")
        calls = []
        candidate = generate_role_narration(
            plan, compile_style_brief("neutral"),
            lambda _: (calls.append(1) or self.response("neutral", "长" * 121 + "[[FACT_000]]")),
        )
        self.assertEqual(candidate.generation_status, "rejected")
        self.assertEqual(candidate.reason_code, "model_connector_text_forbidden")
        self.assertEqual(calls, [1])

    def test_new_story_or_date_is_rejected_even_if_self_check_claims_safe(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。传说它创作于1888年。"))
        result = validate_role_narration(value, plan, brief)
        self.assertEqual(result.validation_status, "rejected")
        self.assertIn(value.reason_code, {"invalid_fact_placeholders", "model_connector_text_forbidden"})

    def test_approved_story_words_inside_immutable_fact_are_accepted(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="ancient_scholar", language="zh",
            budget_seconds=60,
            facts=(NarrationFact(
                "ornament:orn_005", "object_detail",
                "独角狮造型来自审核传说，寓意辟邪保平安。",
            ),),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True,
        )
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(
                plan.style_id, "[[FACT_000]]", ["ornament:orn_005"],
            ),
        )
        result = validate_role_narration(candidate, plan, brief)
        self.assertEqual(result.validation_status, "accepted")
        self.assertTrue(result.same_fact_boundary)

    def test_factual_ancient_connector_remains_visible_to_validation(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="ancient_scholar", language="zh",
            budget_seconds=60,
            facts=(NarrationFact(
                "ornament:orn_005", "object_detail",
                "独角狮造型来自审核传说，寓意辟邪保平安。",
            ),),
            must_include=(), already_covered=(), must_not_claim=(),
            interaction_allowed=True,
        )
        brief = compile_style_brief(plan.style_id)
        candidate = generate_role_narration(
            plan, brief,
            lambda _: self.response(
                plan.style_id, "另有传说称它象征太平。[[FACT_000]]", ["ornament:orn_005"],
            ),
        )
        result = validate_role_narration(candidate, plan, brief)
        self.assertEqual(result.validation_status, "rejected")
        self.assertEqual(candidate.reason_code, "model_connector_text_forbidden")

    def test_unapproved_fact_id_and_internal_fields_are_rejected(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。 source_ids=S1", ["fact:unknown"]))
        result = validate_role_narration(value, plan, brief)
        self.assertIn("fact_id_boundary_violation", result.reason_codes)
        self.assertIn("invalid_fact_id_partition", result.reason_codes)

    def test_internal_field_leak_is_rejected_after_fact_hydration(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan.style_id, "[[FACT_000]]source_ids=S1"),
        )
        self.assertEqual(value.reason_code, "model_connector_text_forbidden")

    def test_listen_only_forbids_questions_and_tasks(self):
        plan = self.plan("listen_only")
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: self.response(plan.style_id, "屋脊可见灰塑。请你拍照好吗？"))
        self.assertEqual(value.generation_status, "rejected")

    def test_model_failure_returns_auditable_rejection(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        value = generate_role_narration(plan, brief, lambda _: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(value.generation_status, "rejected")
        self.assertTrue(value.model_called)

    def test_invalid_schema_fails_closed_without_second_model_call(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        calls = []
        value = generate_role_narration(
            plan, brief, lambda _: (calls.append(1) or '{"unexpected":true}'),
        )
        self.assertEqual(value.generation_status, "rejected")
        self.assertEqual(value.reason_code, "invalid_candidate_schema")
        self.assertEqual(calls, [1])

    def test_all_18_roles_publish_interleaved_fact_blocks(self):
        for style_id in approved_style_ids():
            with self.subTest(style_id=style_id):
                plan = NarrationContentPlan(
                    stop_id="front", style_id=style_id, language="zh", budget_seconds=90,
                    facts=(
                        NarrationFact("fact:a", "craft_background", "审核事实甲。"),
                        NarrationFact("fact:b", "object_detail", "审核事实乙。"),
                        NarrationFact("fact:c", "object_detail", "审核事实丙。"),
                    ),
                    must_include=(), already_covered=(), must_not_claim=(),
                    interaction_allowed=style_id != "listen_only",
                )
                brief = compile_style_brief(style_id)
                candidate = generate_role_narration(
                    plan, brief,
                    lambda _: self.response(style_id, "[[FACT_000]][[FACT_001]][[FACT_002]]", ["fact:a", "fact:b", "fact:c"]),
                )
                result = validate_role_narration(candidate, plan, brief)
                self.assertEqual(result.validation_status, "accepted")
                for fact in plan.facts:
                    self.assertEqual(candidate.public_text.count(fact.statement), 1)
                self.assertTrue(any(value in candidate.public_text for value in brief.point_narration_components["opening"]))
                self.assertTrue(any(value in candidate.public_text for value in brief.point_narration_components["closing"]))

    def test_ancient_scholar_and_cute_junior_cover_building_craft_and_ornament(self):
        facts_by_type = {
            "building": NarrationFact("space:front", "space_identity", "当前讲解点位为前院。"),
            "craft": NarrationFact("craft:灰塑", "craft_background", "灰塑是一种装饰艺术。"),
            "ornament": NarrationFact("ornament:lion", "object_detail", "独角狮是一件灰塑装饰。"),
        }
        for style_id in ("ancient_scholar", "cute_junior"):
            for point_type, fact in facts_by_type.items():
                with self.subTest(style_id=style_id, point_type=point_type):
                    plan = NarrationContentPlan(
                        stop_id="front", style_id=style_id, language="zh", budget_seconds=60,
                        facts=(fact,), must_include=(), already_covered=(), must_not_claim=(),
                        interaction_allowed=True,
                    )
                    brief = compile_style_brief(style_id)
                    candidate = generate_role_narration(
                        plan, brief,
                        lambda _: self.response(style_id, "[[FACT_000]]", [fact.fact_id]),
                    )
                    result = validate_role_narration(candidate, plan, brief)
                    self.assertEqual(result.validation_status, "accepted")
                    self.assertEqual(candidate.public_text.count(fact.statement), 1)
                    self.assertTrue(any(value in candidate.public_text for value in brief.point_narration_components["opening"]))
                    self.assertTrue(any(value in candidate.public_text for value in brief.point_narration_components["closing"]))

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
