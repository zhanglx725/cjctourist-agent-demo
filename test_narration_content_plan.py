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
        }

    def test_plan_contains_only_approved_fact_sections(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=self.audit, visitor_profile={"language": "zh"},
            narration_coverage={"introduced_craft_ids": ["灰塑"]},
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.allocated_content_seconds, 120)
        self.assertEqual([fact.fact_id for fact in plan.facts], ["craft:灰塑", "ornament:lion_01"])
        serialized = str(plan.to_dict())
        self.assertNotIn("观察提示", serialized)
        self.assertNotIn("下一步", serialized)
        self.assertNotIn("source", serialized)

        restored = narration_content_plan_from_dict(plan.to_dict())
        self.assertIsNotNone(restored)
        self.assertEqual(restored.allocated_content_seconds, 120)

    def test_mismatched_reviewed_id_fails_closed(self):
        audit = {**self.audit, "rendered_ornament_ids": ["missing"]}
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=audit, visitor_profile={}, narration_coverage={},
        )
        self.assertEqual(plan.status, "rejected")
        self.assertIn("ornament_section_mismatch", plan.reason_codes)

    def test_listen_only_disables_interaction(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit={**self.audit, "style_id": "listen_only"},
            visitor_profile={}, narration_coverage={},
        )
        self.assertFalse(plan.interaction_allowed)

    def test_known_review_location_boilerplate_is_naturalized_without_fact_drift(self):
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
            render_audit=self.audit, visitor_profile={"language": "zh"},
            narration_coverage={},
        )
        self.assertEqual(plan.status, "ready")
        fact = plan.facts[1]
        self.assertEqual(fact.fact_id, "ornament:lion_01")
        self.assertIn("在建筑山墙垂脊前沿寻找它", fact.statement)
        self.assertIn("找到位置后，再留意它的造型和细节", fact.statement)
        self.assertNotIn("存在审核关联", fact.statement)
        self.assertNotIn("构件位置辨认其造型", fact.statement)


if __name__ == "__main__":
    unittest.main()
