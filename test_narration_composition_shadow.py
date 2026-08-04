"""P3-05 Graph shadow integration for P3 narration composition."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import stop_guidance_node
from controlled_rollout import NARRATION_COMPOSITION, rollout_from_environment
from guidance_policy import build_guidance_policy
from narration_rendering import render_guidance_evidence
from narration_coverage import empty_narration_coverage
from route_planner import plan_template
from tour_interaction import initialize_interaction
from tour_state import start_tour
from visitor_profile import create_visitor_profile


class NarrationCompositionShadowTests(unittest.TestCase):
    def setUp(self):
        tour = start_tour(plan_template("highlights_30"))
        node = tour["remaining_stop_ids"][0]
        self.tour = {**tour, "current_stop_id": node}
        self.interaction = initialize_interaction(self.tour, journey_mode="custom")
        self.profile = create_visitor_profile(
            available_minutes=30, interests=["灰塑"], detail_level="deep"
        ).to_dict()
        from test_e5_narration_rendering import NarrationRenderingTests
        fixture = NarrationRenderingTests(methodName="test_first_craft_precedes_object_and_is_not_repeated")
        fixture.setUp()
        self.program = fixture.program
        self.render = render_guidance_evidence(
            self.program, fixture._bundle(), build_guidance_policy(self.profile)
        )
        self.tour = {**self.tour, "current_stop_id": self.program.node_id}
        self.state = {
            "messages": [HumanMessage(content="开始讲解")],
            "tour_state": self.tour,
            "tour_interaction_state": self.interaction,
            "visitor_profile": self.profile,
            "narration_coverage": empty_narration_coverage().to_dict(),
            "narration_composition_evaluations": [],
            "performance_metrics": [],
        }
        self.env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": NARRATION_COMPOSITION,
        }

    def legacy(self):
        return {
            "message": self.render.visitor_message,
            "status": "guided_e5",
            "stop_program": self.program.to_dict(),
            "evidence": [], "evidence_by_item": {}, "presentation": None,
            "guidance_policy": build_guidance_policy(self.profile).to_dict(),
            "coverage_candidates": [value.to_dict() for value in self.render.eligible_coverage_candidates],
            "narration_render_audit": {
                "node_id": self.program.node_id,
                "rendered_craft_ids": list(self.render.rendered_craft_ids),
                "rendered_ornament_ids": list(self.render.rendered_ornament_ids),
                "used_source_ids": list(self.render.used_source_ids),
                "content_budget_seconds": self.render.content_budget_seconds,
                "allocated_content_seconds": self.render.allocated_content_seconds,
                "omitted_ornament_ids": list(self.render.omitted_ornament_ids),
                "warnings": list(self.render.warnings),
                "style_id": self.render.style_id,
                "style_schema_version": self.render.style_schema_version,
                "style_fallback_used": self.render.style_fallback_used,
                "style_warning_codes": list(self.render.style_warning_codes),
            },
        }

    def test_capability_is_off_by_default_and_shadow_only_when_explicit(self):
        self.assertFalse(rollout_from_environment({}).observes(NARRATION_COMPOSITION))
        with patch.dict(os.environ, self.env, clear=False):
            rollout = rollout_from_environment()
        self.assertTrue(rollout.observes(NARRATION_COMPOSITION))
        self.assertFalse(rollout.enabled(NARRATION_COMPOSITION))

    def test_shadow_preserves_legacy_message_coverage_and_state(self):
        legacy = self.legacy()
        with patch.dict(os.environ, self.env, clear=False), patch(
            "agent_graph.build_stop_guidance", return_value=legacy,
        ):
            update = stop_guidance_node(self.state, {"configurable": {"thread_id": "p3-shadow-a"}})
        self.assertEqual(update["messages"][0].content, legacy["message"])
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        record = update["narration_composition_evaluations"][-1]
        self.assertEqual(record["thread_id"], "p3-shadow-a")
        self.assertEqual(record["validation_status"], "accepted")
        self.assertFalse(record["active_takeover"])
        self.assertTrue(record["legacy_message_preserved"])
        self.assertTrue(record["display_tts_equal"])
        self.assertEqual(record["state_writes"], [])

    def test_off_has_no_shadow_field_and_active_mode_cannot_take_over(self):
        legacy = self.legacy()
        with patch("agent_graph.build_stop_guidance", return_value=legacy), patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "off",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": NARRATION_COMPOSITION,
        }, clear=False):
            off = stop_guidance_node(self.state, {"configurable": {"thread_id": "off"}})
        with patch("agent_graph.build_stop_guidance", return_value=legacy), patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": NARRATION_COMPOSITION,
        }, clear=False):
            active = stop_guidance_node(self.state, {"configurable": {"thread_id": "active"}})
        self.assertNotIn("narration_composition_evaluations", off)
        self.assertNotIn("narration_composition_evaluations", active)
        self.assertEqual(active["messages"][0].content, legacy["message"])

    def test_shadow_failure_is_bounded_and_keeps_legacy_output(self):
        legacy = self.legacy()
        with patch.dict(os.environ, self.env, clear=False), patch(
            "agent_graph.build_stop_guidance", return_value=legacy,
        ), patch(
            "agent_graph.observe_narration_composition", side_effect=ValueError("bad"),
        ):
            update = stop_guidance_node(self.state, {"configurable": {"thread_id": "bad"}})
        self.assertEqual(update["messages"][0].content, legacy["message"])
        record = update["narration_composition_evaluations"][-1]
        self.assertEqual(record["validation_status"], "rejected")
        self.assertEqual(record["rejected_reason"], "observer_unavailable:ValueError")


if __name__ == "__main__":
    unittest.main()
