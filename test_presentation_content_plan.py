from __future__ import annotations

import unittest
from copy import deepcopy

from langchain_core.messages import AIMessage

from agent_graph import _presentation_content_plan_shadow_update
from presentation_content_plan import (
    PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION,
    PresentationContentPlanError,
    build_presentation_content_plan,
    presentation_content_plan_from_dict,
)


SOURCES = {
    "route_planning": ("visitor_profile", "guidance_policy", "route_selection", "route_stop_catalog"),
    "route_opening": ("route_selection", "route_stop_catalog", "tour_opening_evidence"),
    "stop_guidance": ("stop_program", "approved_guidance_evidence", "guidance_policy"),
    "navigation": ("tour_state", "approved_spatial_graph", "route_stop_catalog"),
    "tour_closing": ("visit_summary", "narration_coverage", "tour_state"),
}


class PresentationContentPlanTests(unittest.TestCase):
    def test_all_five_scenes_have_closed_required_structure(self):
        for scene, sources in SOURCES.items():
            with self.subTest(scene=scene):
                plan = build_presentation_content_plan(
                    scene_kind=scene, role_mode="standard", detail_level="standard",
                    budget_seconds=60, source_of_facts=sources,
                )
                self.assertEqual(plan.status, "accepted")
                self.assertEqual(plan.schema_version, PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION)
                self.assertTrue(plan.required_sections)
                self.assertEqual(plan.fallback_mode, "legacy_chain")
                self.assertEqual(plan.state_writes, ())

    def test_all_reviewed_roles_are_plan_valid(self):
        for role in ("ancient_scholar", "child", "listen_only"):
            with self.subTest(role=role):
                plan = build_presentation_content_plan(
                    scene_kind="stop_guidance", role_mode=role, detail_level="standard",
                    budget_seconds=60, source_of_facts=SOURCES["stop_guidance"],
                )
                self.assertEqual(plan.status, "accepted")
                self.assertEqual(plan.role_mode, role)

    def test_listen_only_has_no_observation_or_follow_up_task(self):
        plan = build_presentation_content_plan(
            scene_kind="stop_guidance", role_mode="listen_only", detail_level="standard",
            budget_seconds=60, source_of_facts=SOURCES["stop_guidance"],
        )
        self.assertEqual(plan.observation_tasks, ())
        self.assertNotIn("follow_up_options", plan.optional_sections)

    def test_child_and_ancient_modes_do_not_change_fact_sources_or_add_story(self):
        child = build_presentation_content_plan(
            scene_kind="stop_guidance", role_mode="child", detail_level="standard",
            budget_seconds=60, source_of_facts=SOURCES["stop_guidance"],
        )
        ancient = build_presentation_content_plan(
            scene_kind="stop_guidance", role_mode="ancient_scholar", detail_level="standard",
            budget_seconds=60, source_of_facts=SOURCES["stop_guidance"],
        )
        self.assertEqual(child.source_of_facts, ancient.source_of_facts)
        self.assertNotIn("story", child.required_sections + child.optional_sections)
        self.assertNotIn("story", ancient.required_sections + ancient.optional_sections)

    def test_missing_evidence_and_invalid_contracts_fail_closed(self):
        cases = (
            {"scene_kind": "not_a_scene"},
            {"scene_kind": "stop_guidance", "role_mode": "unknown"},
            {"scene_kind": "stop_guidance", "detail_level": "verbose"},
        )
        for case in cases:
            kwargs = {
                "scene_kind": case.get("scene_kind", "stop_guidance"),
                "role_mode": case.get("role_mode", "standard"),
                "detail_level": case.get("detail_level", "standard"),
                "budget_seconds": 60,
                "source_of_facts": SOURCES["stop_guidance"],
            }
            with self.subTest(case=case):
                self.assertEqual(build_presentation_content_plan(**kwargs).status, "rejected")
        self.assertEqual(build_presentation_content_plan(
            scene_kind="stop_guidance", budget_seconds=60,
            source_of_facts=SOURCES["stop_guidance"], evidence_available=False,
        ).reason_codes, ("evidence_missing",))
        self.assertEqual(build_presentation_content_plan(
            scene_kind="stop_guidance", budget_seconds=0,
            source_of_facts=SOURCES["stop_guidance"],
        ).status, "rejected")

    def test_internal_source_or_state_fields_are_rejected(self):
        with self.assertRaises(PresentationContentPlanError):
            presentation_content_plan_from_dict({"schema_version": PRESENTATION_CONTENT_PLAN_SCHEMA_VERSION, "node_id": "x"})
        valid = build_presentation_content_plan(
            scene_kind="stop_guidance", budget_seconds=60, source_of_facts=SOURCES["stop_guidance"],
        ).to_dict()
        invalid = deepcopy(valid)
        invalid["state_writes"] = ["tour_state"]
        with self.assertRaises(PresentationContentPlanError):
            presentation_content_plan_from_dict(invalid)
        invalid = deepcopy(valid)
        invalid["source_of_facts"] = ["source_ids"]
        with self.assertRaises(PresentationContentPlanError):
            presentation_content_plan_from_dict(invalid)
        invalid = deepcopy(valid)
        invalid["budget_seconds"] = "60"
        with self.assertRaises(PresentationContentPlanError):
            presentation_content_plan_from_dict(invalid)

    def test_shadow_plan_preserves_legacy_and_operational_state(self):
        state = {
            "messages": [AIMessage(content="旧链讲解", additional_kwargs={"stop_guidance": True})],
            "visitor_profile": {"detail_level": "standard"},
            "active_stop_program": {"budget_seconds": 90},
            "active_guidance_evidence_by_item": {},
            "active_narration_render_audit": {"status": "accepted"},
            "role_mode_shadow": {"selected_style_id": "child"},
            "performance_metrics": [],
        }
        before = deepcopy(state)
        update = _presentation_content_plan_shadow_update(state, {})
        plan = update["presentation_content_plan"]
        self.assertEqual(plan["scene_kind"], "stop_guidance")
        self.assertEqual(plan["role_mode"], "child")
        self.assertEqual(update["presentation_content_plan_evaluations"][-1]["active_takeover"], False)
        self.assertTrue(update["presentation_content_plan_evaluations"][-1]["legacy_message_preserved"])
        self.assertEqual(state, before)
        for forbidden in ("tour_state", "visitor_profile", "active_route_plan", "pending_replan_proposal"):
            self.assertNotIn(forbidden, update)


if __name__ == "__main__":
    unittest.main()
