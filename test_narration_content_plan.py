from __future__ import annotations

import unittest

from narration_content_plan import build_narration_content_plan


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
        }

    def test_plan_contains_only_approved_fact_sections(self):
        plan = build_narration_content_plan(
            public_message=self.message, stop_program=self.program,
            render_audit=self.audit, visitor_profile={"language": "zh"},
            narration_coverage={"introduced_craft_ids": ["灰塑"]},
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual([fact.fact_id for fact in plan.facts], ["craft:灰塑", "ornament:lion_01"])
        serialized = str(plan.to_dict())
        self.assertNotIn("观察提示", serialized)
        self.assertNotIn("下一步", serialized)
        self.assertNotIn("source", serialized)

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


if __name__ == "__main__":
    unittest.main()
