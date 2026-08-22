from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent_graph import (
    qa_content_plan_node,
    qa_role_narration_generation_node,
    qa_role_narration_commit_node,
    qa_role_narration_fallback_node,
    qa_role_narration_validation_node,
    route_after_qa_role_narration_validation,
)
from langchain_core.messages import AIMessage
from role_narration_generation import RoleNarrationCandidate
from test_qa_role_shadow import QaRoleShadowTests


ACTIVE_ENV = {
    "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
    "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_qa",
    "PRODUCT_ROLE_ACTIVE_ENABLED": "true",
    "PRODUCT_ROLE_ACTIVE_STYLES": "child,professional",
    "PRODUCT_ROLE_ACTIVE_SCENES": "tour_qa,qa_follow_up_detail",
    "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "100",
    "PRODUCT_ROLE_KILL_SWITCH": "false",
    "PRODUCT_ROLE_VALIDATION_LEVEL": "strict",
    "PRODUCT_ROLE_FALLBACK_POLICY": "legacy",
}


class QaRoleActiveTests(unittest.TestCase):
    def _accepted(self, *, follow_up=False):
        fixture = QaRoleShadowTests()
        state = fixture.state("professional" if follow_up else "child", follow_up=follow_up)
        planned = {**state, **qa_content_plan_node(state)}
        narration_plan = planned["qa_content_plan"]["narration_plan"]
        approved = narration_plan["facts"][0]["statement"]
        candidate = fixture.generated(narration_plan["style_id"], f"先抓住重点。{approved}")
        generated = {"qa_role_narration_candidate": candidate.to_dict()}
        merged = {**planned, **generated}
        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            validated = qa_role_narration_validation_node(
                merged, {"configurable": {"thread_id": "qa-active-1"}},
            )
        return {**merged, **validated}, approved

    def test_tour_qa_active_publishes_only_validated_candidate(self):
        state, approved = self._accepted()
        self.assertEqual(route_after_qa_role_narration_validation(state), "qa_role_narration_commit")
        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            result = qa_role_narration_commit_node(state)
        self.assertIn(approved, result["messages"][0].content)
        self.assertTrue(result["messages"][0].additional_kwargs["tour_qa_answer"])
        self.assertTrue(result["messages"][0].additional_kwargs["qa_role_narration"])
        self.assertTrue(result["active_qa_role_narration_audit"]["active_takeover"])
        for forbidden in ("tour_state", "qa_context", "retrieved_evidence", "narration_coverage"):
            self.assertNotIn(forbidden, result)

    def test_normal_qa_keeps_direct_answer_without_selected_tour_persona(self):
        fixture = QaRoleShadowTests()
        source = fixture.state("child")
        planned = {**source, **qa_content_plan_node(source)}
        narration_plan = planned["qa_content_plan"]["narration_plan"]
        approved = narration_plan["facts"][0]["statement"]
        raw_candidate = fixture.generated(
            narration_plan["style_id"], f"眼光看过来。{approved}",
        )
        with patch.dict(os.environ, ACTIVE_ENV, clear=False), patch(
            "agent_graph.generate_role_narration", return_value=raw_candidate,
        ):
            generated = qa_role_narration_generation_node(planned)
            validated = qa_role_narration_validation_node(
                {**planned, **generated},
                {"configurable": {"thread_id": "qa-direct-answer"}},
            )
            state = {**planned, **generated, **validated}
            result = qa_role_narration_commit_node(state)
        self.assertEqual(result["messages"][0].content, approved)
        self.assertNotIn("眼光看过来", result["messages"][0].content)

    def test_follow_up_uses_its_own_product_scene(self):
        state, _ = self._accepted(follow_up=True)
        self.assertEqual(state["active_qa_role_narration_audit"]["scene_kind"], "qa_follow_up_detail")
        self.assertEqual(route_after_qa_role_narration_validation(state), "qa_role_narration_commit")

    def test_multiline_legacy_answer_keeps_layout_and_publishes_role_candidate(self):
        fixture = QaRoleShadowTests()
        state = fixture.state("child")
        approved = (
            "灰塑是珠江三角洲传统建筑中广泛使用的装饰艺术。\n\n"
            "在材料与制作上，艺人以石灰为主料。\n\n"
            "现场可见情况请以实际为准。"
        )
        state["messages"] = [AIMessage(
            content=approved,
            additional_kwargs={"tour_qa_answer": True},
        )]
        planned = {**state, **qa_content_plan_node(state)}
        narration_plan = planned["qa_content_plan"]["narration_plan"]
        raw_candidate = RoleNarrationCandidate(
            style_id="child",
            public_text=approved,
            used_fact_ids=("qa:approved_answer",),
            omitted_fact_ids=(),
            self_check={
                "added_new_facts": False,
                "role_consistent": True,
                "within_budget": True,
            },
            model_called=True,
            latency_ms=1,
        )
        with patch.dict(os.environ, ACTIVE_ENV, clear=False), patch(
            "agent_graph.generate_role_narration", return_value=raw_candidate,
        ):
            generated = qa_role_narration_generation_node(planned)
            merged = {**planned, **generated}
            validated = qa_role_narration_validation_node(
                merged, {"configurable": {"thread_id": "qa-active-multiline"}},
            )
            committed = qa_role_narration_commit_node({**merged, **validated})

        validation = validated["qa_role_narration_validation"]
        self.assertEqual(validation["validation_status"], "accepted")
        self.assertTrue(validation["layout_passed"])
        self.assertEqual(validation["layout_reason_codes"], [])
        self.assertEqual(
            committed["messages"][0].content.count(approved), 1,
        )
        self.assertTrue(committed["active_qa_role_narration_audit"]["active_takeover"])
        self.assertFalse(committed["active_qa_role_narration_audit"]["fallback_used"])
        self.assertEqual(
            committed["active_qa_role_narration_audit"]["commit_decision"],
            "qa_role_candidate_published",
        )
        self.assertEqual(validation["state_writes"], [])

    def test_newline_added_by_role_connector_is_rejected(self):
        fixture = QaRoleShadowTests()
        state = fixture.state("child")
        planned = {**state, **qa_content_plan_node(state)}
        narration_plan = planned["qa_content_plan"]["narration_plan"]
        approved = narration_plan["facts"][0]["statement"]
        candidate = fixture.generated("child", f"先看这里。\n{approved}本次回答到这里。")
        merged = {
            **planned,
            "qa_role_narration_candidate": candidate.to_dict(),
        }
        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            validated = qa_role_narration_validation_node(
                merged, {"configurable": {"thread_id": "qa-active-newline"}},
            )
        validation = validated["qa_role_narration_validation"]
        self.assertEqual(validation["validation_status"], "rejected")
        self.assertIn("layout_not_continuous", validation["reason_codes"])
        self.assertTrue(validated["active_qa_role_narration_audit"]["fallback_used"])

    def test_rejection_and_kill_switch_preserve_legacy_answer(self):
        state, _ = self._accepted()
        state["qa_role_narration_validation"] = {
            "validation_status": "rejected", "reason_codes": ["fact_id_boundary_violation"],
        }
        self.assertEqual(route_after_qa_role_narration_validation(state), "qa_role_narration_fallback")
        fallback = qa_role_narration_fallback_node(state)
        self.assertNotIn("messages", fallback)
        self.assertTrue(fallback["active_qa_role_narration_audit"]["legacy_message_preserved"])

        killed = {**ACTIVE_ENV, "PRODUCT_ROLE_KILL_SWITCH": "true"}
        with patch.dict(os.environ, killed, clear=False):
            result = qa_role_narration_commit_node(state)
        self.assertNotIn("messages", result)
        self.assertEqual(result["active_qa_role_narration_audit"]["commit_decision"], "legacy_qa_preserved")


if __name__ == "__main__":
    unittest.main()
