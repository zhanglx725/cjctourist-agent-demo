from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent_graph import (
    qa_content_plan_node,
    qa_role_narration_generation_node,
    qa_role_narration_validation_node,
)
from role_narration_generation import RoleNarrationCandidate


class QaRoleShadowTests(unittest.TestCase):
    def state(self, style_id: str = "child", *, follow_up: bool = False):
        message = "灰塑是岭南建筑中常见的装饰工艺。"
        return {
            "messages": [AIMessage(
                content=message,
                additional_kwargs={
                    "tour_qa_answer": True,
                    **({"qa_follow_up_detail": True} if follow_up else {}),
                },
            )],
            "visitor_profile": {"language": "zh"},
            "role_mode_shadow": {
                "status": "selected",
                "selected_style_id": style_id,
                "source": "visitor_profile",
                "confidence": 0.95,
            },
            "tour_state": {"current_stop_id": "unchanged"},
            "tour_interaction_state": {"status": "unchanged"},
            "active_route_plan": {"route_id": "unchanged"},
            "pending_replan_proposal": {"status": "unchanged"},
            "narration_coverage": {"introduced_craft_ids": ["灰塑"]},
            "performance_metrics": [],
            "qa_role_narration_evaluations": [],
        }

    @staticmethod
    def generated(style_id: str, public_text: str) -> RoleNarrationCandidate:
        return RoleNarrationCandidate(
            style_id=style_id,
            public_text=public_text,
            used_fact_ids=("qa:approved_answer",),
            omitted_fact_ids=(),
            self_check={
                "added_new_facts": False,
                "role_consistent": True,
                "within_budget": True,
            },
            model_called=True,
            latency_ms=5,
        )

    def run_shadow(self, state):
        plan_update = qa_content_plan_node(state)
        planned = {**state, **plan_update}
        plan = plan_update["qa_content_plan"]["narration_plan"]
        approved = plan["facts"][0]["statement"]
        style_id = plan["style_id"]
        candidate = self.generated(style_id, f"先抓住重点。{approved}")
        with patch.dict("os.environ", {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_qa",
        }, clear=False), patch(
            "agent_graph.generate_role_narration", return_value=candidate,
        ):
            generated = qa_role_narration_generation_node(planned)
        validated = qa_role_narration_validation_node({**planned, **generated})
        return plan_update, generated, validated

    def test_tour_qa_child_candidate_is_shadow_only(self):
        state = self.state("child")
        before = deepcopy(state)
        plan, generated, validated = self.run_shadow(state)
        self.assertEqual(plan["qa_content_plan"]["scene_kind"], "tour_qa")
        self.assertEqual(
            generated["qa_role_narration_candidate"]["generation_status"],
            "generated",
        )
        audit = validated["active_qa_role_narration_audit"]
        self.assertEqual(audit["validation_status"], "accepted")
        self.assertTrue(audit["same_fact_boundary"])
        self.assertTrue(audit["public_message_safe"])
        self.assertTrue(audit["role_consistent"])
        self.assertTrue(audit["within_budget"])
        self.assertFalse(audit["active_takeover"])
        self.assertEqual(audit["state_writes"], [])
        self.assertTrue(audit["legacy_message_preserved"])
        self.assertTrue(audit["same_public_message"])
        self.assertEqual(state, before)
        for forbidden in (
            "tour_state", "visitor_profile", "active_route_plan",
            "pending_replan_proposal", "narration_coverage", "messages",
        ):
            self.assertNotIn(forbidden, generated)
            self.assertNotIn(forbidden, validated)

    def test_follow_up_inherits_professional_role_and_scope(self):
        state = self.state("professional", follow_up=True)
        plan, _, validated = self.run_shadow(state)
        self.assertEqual(
            plan["qa_content_plan"]["scene_kind"], "qa_follow_up_detail"
        )
        self.assertEqual(
            plan["qa_content_plan"]["narration_plan"]["style_id"],
            "professional",
        )
        self.assertEqual(
            validated["active_qa_role_narration_audit"]["validation_status"],
            "accepted",
        )

    def test_listen_only_plan_disallows_interaction(self):
        state = self.state("listen_only")
        plan = qa_content_plan_node(state)["qa_content_plan"]
        self.assertFalse(plan["narration_plan"]["interaction_allowed"])

    def test_invalid_candidate_fails_closed_and_preserves_answer(self):
        state = self.state("child")
        plan_update = qa_content_plan_node(state)
        planned = {**state, **plan_update}
        rejected = RoleNarrationCandidate(
            style_id="child", public_text="", used_fact_ids=(),
            omitted_fact_ids=(), self_check={}, model_called=True,
            latency_ms=5, generation_status="rejected",
            reason_code="invalid_candidate_schema",
        )
        with patch.dict("os.environ", {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_qa",
        }, clear=False), patch(
            "agent_graph.generate_role_narration", return_value=rejected,
        ):
            generated = qa_role_narration_generation_node(planned)
        validated = qa_role_narration_validation_node({**planned, **generated})
        audit = validated["active_qa_role_narration_audit"]
        self.assertEqual(audit["validation_status"], "rejected")
        self.assertTrue(audit["fallback_used"])
        self.assertTrue(audit["legacy_message_preserved"])
        self.assertTrue(audit["same_public_message"])
        self.assertFalse(audit["active_takeover"])
        self.assertNotIn("messages", validated)


if __name__ == "__main__":
    unittest.main()
