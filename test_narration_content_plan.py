from __future__ import annotations

import unittest

from narration_content_plan import (
    build_narration_content_plan,
    narration_content_plan_from_dict,
)


class NarrationContentPlanTests(unittest.TestCase):
    def setUp(self):
        self.message = (
            "【工艺背景：灰塑】\n\n灰塑是建筑装饰工艺。\n\n"
            "【观察对象：独角狮】\n\n独角狮位于屋脊。\n\n"
            "【观察提示】\n\n可以留意轮廓。\n\n"
            "【下一步】\n\n讲解结束后可继续。"
        )
        self.program = {
            "node_id": "front_courtyard_center",
            "selected_items": [{"ornament_id": "lion_01", "name": "独角狮"}],
        }
        self.audit = {
            "style_id": "ancient_scholar",
            "rendered_craft_ids": ["灰塑"],
            "rendered_ornament_ids": ["lion_01"],
            "content_budget_seconds": 180,
            "allocated_content_seconds": 120,
            "fact_units": [
                {"unit_id": "craft:灰塑", "topic_kind": "craft", "required": True,
                 "statements": ["灰塑是建筑装饰工艺。"]},
                {"unit_id": "ornament:lion_01", "topic_kind": "ornament", "required": True,
                 "statements": ["独角狮位于屋脊。"]},
            ],
        }

    def test_plan_contains_only_approved_fact_sections(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=self.audit, visitor_profile={"language": "zh"},
            narration_coverage={"introduced_craft_ids": ["灰塑"]},
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.allocated_content_seconds, 120)
        self.assertEqual([fact.fact_id for fact in plan.facts], ["craft:灰塑:000", "ornament:lion_01:000"])
        serialized = str(plan.to_dict())
        self.assertNotIn("观察提示", serialized)
        self.assertNotIn("下一步", serialized)
        self.assertNotIn("source", serialized)

        restored = narration_content_plan_from_dict(plan.to_dict())
        self.assertIsNotNone(restored)
        self.assertEqual(restored.allocated_content_seconds, 120)

    def test_optional_dimension_is_a_non_required_audited_fact_unit(self):
        audit = {
            **self.audit,
            "rendered_dimension_ids": ["knowledge_deadbeef"],
            "fact_units": [
                *self.audit["fact_units"],
                {
                    "unit_id": "dimension:knowledge_deadbeef",
                    "topic_kind": "dimension",
                    "required": False,
                    "statements": ["馆方历史资料记录了这一装饰的保护案例。"],
                },
            ],
        }
        plan = build_narration_content_plan(
            public_message=self.message,
            stop_program=self.program,
            render_audit=audit,
            visitor_profile={},
            narration_coverage={},
        )
        self.assertEqual(plan.status, "ready")
        optional = next(fact for fact in plan.facts if fact.fact_id.startswith("dimension:"))
        self.assertFalse(optional.required)
        self.assertEqual(optional.topic_kind, "ornament")

    def test_mismatched_reviewed_id_fails_closed(self):
        audit = {**self.audit, "rendered_ornament_ids": ["missing"]}
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=audit, visitor_profile={}, narration_coverage={},
        )
        self.assertEqual(plan.status, "rejected")
        self.assertIn("fact_unit_subject_mismatch", plan.reason_codes)

    def test_listen_only_disables_interaction(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit={**self.audit, "style_id": "listen_only"},
            visitor_profile={}, narration_coverage={},
        )
        self.assertFalse(plan.interaction_allowed)

    def test_explicit_craft_request_excludes_unrelated_ornament_story(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=self.audit, visitor_profile={}, narration_coverage={},
            request_text="请以古风书生风格讲解这里的灰塑工艺",
        )
        self.assertEqual(plan.requested_scope, "craft")
        self.assertEqual([fact.fact_id for fact in plan.facts], ["craft:灰塑:000"])

    def test_explicit_space_request_never_expands_to_craft_or_ornament(self):
        plan = build_narration_content_plan(
            public_message=self.message,
            stop_program={**self.program, "display_name": "前院中部"},
            render_audit=self.audit, visitor_profile={}, narration_coverage={},
            request_text="请以古风书生风格讲解这里的建筑空间",
        )
        self.assertEqual(plan.requested_scope, "space")
        self.assertEqual([fact.fact_id for fact in plan.facts], ["space:front_courtyard_center"])

    def test_audited_location_statement_is_already_visitor_safe_in_the_plan(self):
        message = (
            "【工艺背景：灰塑】\n\n灰塑是建筑装饰工艺。\n\n"
            "【观察对象：独角狮】\n\n"
            "独角狮是一件灰塑装饰。"
            "它与建筑山墙垂脊前沿存在审核关联；可结合现场标识观察。"
            "观察时，可结合建筑山墙垂脊前沿处的构件位置辨认其造型。\n\n"
            "【下一步】\n\n讲解结束后可继续。"
        )
        plan = build_narration_content_plan(
            public_message=message, stop_program=self.program,
            render_audit={**self.audit, "fact_units": [
                self.audit["fact_units"][0],
                {"unit_id": "ornament:lion_01", "topic_kind": "ornament", "required": True,
                 "statements": [
                    "独角狮是一件灰塑装饰。",
                    "它与建筑山墙垂脊前沿存在审核关联；可结合现场标识观察。",
                    "观察时，可结合建筑山墙垂脊前沿处的构件位置辨认其造型。",
                 ]},
            ]}, visitor_profile={"language": "zh"},
            narration_coverage={},
        )
        self.assertEqual(plan.status, "ready")
        # Content plans only consume public fact units.  Source wording is
        # retained in render audit, never allowed to reach role generation.
        self.assertEqual(plan.facts[2].statement, "它与建筑山墙垂脊前沿存在审核关联；可结合现场标识观察。")
        self.assertEqual(plan.facts[3].statement, "观察时，可结合建筑山墙垂脊前沿处的构件位置辨认其造型。")

    def test_buddy_plan_starts_with_first_visible_object_unit(self):
        plan = build_narration_content_plan(
            public_message=self.message,
            stop_program=self.program,
            render_audit={**self.audit, "style_id": "buddy_guide"},
            visitor_profile={}, narration_coverage={},
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual(
            [fact.fact_id for fact in plan.facts],
            ["ornament:lion_01:000", "craft:灰塑:000"],
        )


if __name__ == "__main__":
    unittest.main()
