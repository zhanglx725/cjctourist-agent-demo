"""Offline C7 integration tests for policy-bound programs and narration."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from guide_program_evidence import build_stop_guidance
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import load_guide_cards
from route_planner import plan_template
from tour_state import start_tour
from visitor_profile import create_visitor_profile


EVIDENCE = {
    "document": "07_ornament_crafts.md",
    "title_path": ["陈家祠建筑装饰工艺总览", "测试条目"],
    "source_ids": ["S10"],
    "content": "馆方资料说明，这件装饰具有清晰的造型层次。",
}


def _rag(_: str) -> str:
    return json.dumps({"evidence": [EVIDENCE]}, ensure_ascii=False)


class GuidancePolicyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        initial = start_tour(plan_template("highlights_30"), interests=["灰塑"], detail_level="standard")
        interaction = initialize_interaction(initial)
        arrived = handle_tour_event(initial, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        self.tour = arrived["tour_state"]
        self.interaction = arrived["interaction_state"]
        self.allowed_ids = {
            item["ornament_id"]
            for item in load_guide_cards()["stop_front_courtyard_center"]["ornaments"]
        }

    def _profile(self, **changes: str) -> dict:
        base = create_visitor_profile(interests=["灰塑"], detail_level="standard")
        return create_visitor_profile(**{**base.to_dict(), **changes}).to_dict()

    def _guidance(self, **changes: str) -> dict:
        before_tour = deepcopy(self.tour)
        before_interaction = deepcopy(self.interaction)
        result = build_stop_guidance(
            self.tour, self.interaction, _rag, visitor_profile=self._profile(**changes)
        )
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)
        self.assertEqual(result["status"], "guided")
        self.assertTrue(result["guidance_policy"]["fact_evidence_required"])
        self.assertEqual(result["guidance_policy"]["budget_cap_mode"], "min_with_stop_budget")
        program = result["stop_program"]
        self.assertLessEqual(len(program["selected_items"]), result["guidance_policy"]["max_items_per_stop"])
        self.assertLessEqual(sum(item["planned_seconds"] for item in program["selected_items"]), program["budget_seconds"])
        self.assertTrue(all(item["ornament_id"] in self.allowed_ids for item in program["selected_items"]))
        return result

    def test_default_and_child_story_keep_same_facts_and_sources(self):
        default = self._guidance()
        child = self._guidance(
            audience_mode="child_friendly", explanation_style="story", interaction_mode="interactive_tasks"
        )
        self.assertEqual(
            [item["ornament_id"] for item in default["stop_program"]["selected_items"]],
            [item["ornament_id"] for item in child["stop_program"]["selected_items"]],
        )
        self.assertEqual(default["source_ids"], child["source_ids"])
        self.assertEqual(default["evidence"], child["evidence"])
        self.assertIn("小任务：", child["message"])
        self.assertNotIn("构件", child["message"])

    def test_family_study_professional_and_mixed_modes_change_expression_only(self):
        family = self._guidance(audience_mode="family")
        study = self._guidance(audience_mode="study", knowledge_level="enthusiast", interaction_mode="interactive_tasks")
        professional = self._guidance(
            detail_level="short", knowledge_level="professional", explanation_style="technical"
        )
        mixed = self._guidance(audience_mode="mixed_group")
        self.assertIn("大家可以一起", family["message"])
        self.assertIn("观察目标", study["message"])
        self.assertNotIn("S10", study["message"])
        self.assertIn("S10", study["source_ids"])
        self.assertEqual(len(professional["stop_program"]["selected_items"]), 1)
        self.assertIn("从工艺与构件关系", professional["message"])
        self.assertNotIn("S10", professional["message"])
        self.assertIn("S10", professional["source_ids"])
        self.assertIn("通俗方式", mixed["message"])
        self.assertIn("更深入的工艺补充", mixed["message"])

    def test_listen_only_overrides_child_interaction_task(self):
        result = self._guidance(
            audience_mode="child_friendly", explanation_style="interactive", interaction_mode="listen_only"
        )
        self.assertFalse(result["guidance_policy"]["interaction_task_enabled"])
        self.assertFalse(result["guidance_policy"]["proactive_question_enabled"])
        self.assertNotIn("小任务：", result["message"])
        self.assertNotIn("观察任务：", result["message"])
        self.assertNotIn("思考任务：", result["message"])

    def test_deep_policy_cannot_exceed_reviewed_stop_budget(self):
        result = self._guidance(detail_level="deep", knowledge_level="professional")
        program = result["stop_program"]
        self.assertLessEqual(len(program["selected_items"]), 3)
        self.assertLessEqual(program["allocated_content_seconds"], program["budget_seconds"])
        self.assertTrue(result["guidance_policy"]["comparison_enabled"])
        self.assertTrue(result["guidance_policy"]["research_extension_enabled"])

    def test_custom_session_derives_detailed_policy_without_profile_or_state_write(self):
        before_tour = deepcopy(self.tour)
        before_interaction = deepcopy(self.interaction)
        custom_interaction = {**self.interaction, "journey_mode": "custom"}
        profile = self._profile(detail_level="standard", interaction_mode="listen_only")
        result = build_stop_guidance(self.tour, custom_interaction, _rag, visitor_profile=profile)

        self.assertEqual(result["guidance_policy"]["explanation_length"], "detailed")
        self.assertEqual(result["stop_program"]["detail_level"], "deep")
        self.assertLessEqual(
            result["stop_program"]["allocated_content_seconds"],
            result["stop_program"]["budget_seconds"],
        )
        self.assertFalse(result["guidance_policy"]["interaction_task_enabled"])
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)
        self.assertEqual(profile["detail_level"], "standard")


if __name__ == "__main__":
    unittest.main()
