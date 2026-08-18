from __future__ import annotations

import json
import unittest
import os
from unittest.mock import patch

from narration_content_plan import build_narration_content_plan
from narration_style_policy import compile_style_brief
from narration_validation import validate_role_narration
from role_narration_generation import RoleNarrationCandidate, generate_role_narration


class ContinuousPointNarrationTests(unittest.TestCase):
    def setUp(self):
        self._natural_env = patch.dict(os.environ, {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "false",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "false",
        }, clear=False)
        self._natural_env.start()

    def tearDown(self):
        self._natural_env.stop()

    def plan(self, request_text: str = ""):
        return build_narration_content_plan(
            public_message="【工艺背景：木雕】旧链栏目正文。",
            stop_program={
                "node_id": "front", "display_name": "前院",
                "selected_items": [{"ornament_id": "orn_1", "name": "杏林春燕"}],
            },
            render_audit={
                "style_id": "cute_junior", "content_budget_seconds": 180,
                "allocated_content_seconds": 60,
                "rendered_craft_ids": ["木雕"], "rendered_ornament_ids": ["orn_1"],
                "fact_units": [
                    {"unit_id": "craft:木雕", "topic_kind": "craft", "required": True,
                     "statements": ["木雕事实一。", "木雕事实二。"]},
                    {"unit_id": "ornament:orn_1", "topic_kind": "ornament", "required": True,
                     "statements": ["杏林春燕事实一。", "杏林春燕事实二。"]},
                ],
            },
            visitor_profile={"language": "zh"}, narration_coverage={},
            request_text=request_text,
        )

    @staticmethod
    def response(plan, tokens: str):
        return json.dumps({
            "schema_version": "role_narration_candidate_v1",
            "style_id": plan.style_id,
            "public_text": tokens,
            "used_fact_ids": [fact.fact_id for fact in plan.facts],
            "omitted_fact_ids": [],
            "self_check": {"added_new_facts": False, "role_consistent": True, "within_budget": True},
        }, ensure_ascii=False)

    def test_audited_fact_units_replace_legacy_headings_and_old_style_prose(self):
        plan = self.plan()
        self.assertEqual([fact.topic_kind for fact in plan.facts], ["craft", "craft", "ornament", "ornament"])
        self.assertNotIn("旧链栏目正文", "".join(fact.statement for fact in plan.facts))
        candidate = generate_role_narration(
            plan, compile_style_brief(plan.style_id),
            lambda _: self.response(plan, "".join(f"[[FACT_{index:03d}]]" for index in range(len(plan.facts)))),
        )
        validation = validate_role_narration(candidate, plan, compile_style_brief(plan.style_id))
        self.assertEqual(validation.validation_status, "accepted")
        self.assertTrue(validation.layout_passed)
        self.assertNotIn("【", candidate.public_text)
        for fact in plan.facts:
            self.assertEqual(candidate.public_text.count(fact.statement), 1)

    def test_explicit_scope_keeps_all_matching_reviewed_statements(self):
        craft = self.plan("请讲解这里的木雕工艺")
        self.assertEqual([fact.statement for fact in craft.facts], ["木雕事实一。", "木雕事实二。"])
        ornament = self.plan("请讲解这里的纹样对象")
        self.assertEqual([fact.statement for fact in ornament.facts], ["杏林春燕事实一。", "杏林春燕事实二。"])

    def test_model_fact_order_and_connector_text_fail_closed(self):
        plan = self.plan()
        brief = compile_style_brief(plan.style_id)
        wrong_order = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan, "[[FACT_001]][[FACT_000]][[FACT_002]][[FACT_003]]"),
        )
        self.assertEqual(wrong_order.reason_code, "invalid_fact_token_order")
        free_text = generate_role_narration(
            plan, brief,
            lambda _: self.response(plan, "[[FACT_000]]～[[FACT_001]][[FACT_002]][[FACT_003]]"),
        )
        self.assertEqual(free_text.reason_code, "model_connector_text_forbidden")

    def test_layout_and_topic_mismatch_reason_codes_are_auditable(self):
        plan = self.plan("请讲解这里的木雕工艺")
        brief = compile_style_brief(plan.style_id)
        bad = RoleNarrationCandidate(
            style_id=plan.style_id,
            public_text=(
                f"{brief.point_narration_components['opening'][0]}【工艺背景】"
                f"{brief.point_narration_components['ornament_intro'][0]}{plan.facts[0].statement}"
                f"{brief.point_narration_components['ornament_observation'][0]}{plan.facts[1].statement}"
                f"{brief.point_narration_components['closing'][0]}"
            ),
            used_fact_ids=tuple(fact.fact_id for fact in plan.facts), omitted_fact_ids=(),
            self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
            model_called=False, latency_ms=0,
        )
        result = validate_role_narration(bad, plan, brief)
        self.assertEqual(result.validation_status, "rejected")
        self.assertIn("layout_heading_leak", result.reason_codes)
        self.assertIn("craft_style_coverage_incomplete", result.reason_codes)
        self.assertIn("style_component_topic_mismatch", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
