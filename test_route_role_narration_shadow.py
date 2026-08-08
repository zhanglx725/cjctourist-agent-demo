from __future__ import annotations

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    atomic_read_plan_shadow_node,
    direct_route_node,
    tour_event_node,
    tour_opening_node,
)
from presentation_content_plan import build_presentation_content_plan
from route_role_narration_shadow import (
    build_route_role_text_candidate,
    validate_route_role_text_candidate,
)


SOURCES = {
    "route_planning": ("visitor_profile", "guidance_policy", "route_selection", "route_stop_catalog"),
    "route_opening": ("route_selection", "route_stop_catalog", "tour_opening_evidence"),
}


def _plan(scene: str, role: str):
    return build_presentation_content_plan(
        scene_kind=scene,
        role_mode=role,
        detail_level="standard",
        budget_seconds=600,
        source_of_facts=SOURCES[scene],
    )


class RouteRoleNarrationShadowTests(unittest.TestCase):
    def test_all_reviewed_roles_generate_valid_candidates_for_both_surfaces(self):
        legacy = "路线主题已确定。第一站为前院中部。请以现场安排为准。"
        for scene in SOURCES:
            for role in ("standard", "ancient_scholar", "child", "listen_only"):
                with self.subTest(scene=scene, role=role):
                    candidate = build_route_role_text_candidate(
                        scene_kind=scene, role_mode=role, legacy_text=legacy,
                    )
                    result = validate_route_role_text_candidate(
                        candidate, plan=_plan(scene, role), legacy_text=legacy,
                    )
                    self.assertEqual(result["validation_status"], "accepted")
                    self.assertTrue(result["legacy_message_preserved"])
                    self.assertEqual(result["fact_diff"], [])
                    self.assertEqual(result["route_diff"], [])
                    self.assertEqual(result["safety_diff"], [])
                    self.assertEqual(result["state_writes"], [])

    def test_candidate_must_preserve_complete_legacy_message(self):
        legacy = "总时长30分钟。第一站为前院中部。请以现场安排为准。"
        candidate = build_route_role_text_candidate(
            scene_kind="route_planning", role_mode="ancient_scholar", legacy_text=legacy,
        )
        candidate["public_text"] = "请随我观览。第一站为前院中部。"
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("route_planning", "ancient_scholar"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "rejected")
        self.assertIn("legacy_boundary_or_role_template_mismatch", result["reason_codes"])

    def test_internal_fields_and_invalid_schema_fail_closed(self):
        legacy = "路线已确认。"
        invalid = {
            "schema_version": "route_role_text_candidate_v1",
            "scene_kind": "route_planning",
            "role_mode": "standard",
            "public_text": legacy + " source_ids=S01",
            "state_patch": {"tour_state": {}},
        }
        result = validate_route_role_text_candidate(
            invalid, plan=_plan("route_planning", "standard"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "rejected")
        self.assertIn("invalid_candidate_schema", result["reason_codes"])

    def test_listen_only_rejects_an_added_question_or_task(self):
        legacy = "路线已确认。"
        candidate = build_route_role_text_candidate(
            scene_kind="route_opening", role_mode="listen_only", legacy_text=legacy,
        )
        candidate["public_text"] += "请你回答好吗？"
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("route_opening", "listen_only"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "rejected")
        self.assertIn("listen_only_interaction_violation", result["reason_codes"])

    def test_route_planning_shadow_preserves_legacy_route_and_operational_state(self):
        route = direct_route_node({
            "messages": [HumanMessage(content="我有30分钟，喜欢灰塑，帮我规划路线")],
            "visitor_profile": {
                "available_minutes": 30, "interests": ["灰塑"],
                "detail_level": "standard", "route_constraint": None,
            },
            "role_mode_shadow": {"status": "selected", "selected_style_id": "ancient_scholar"},
        })
        state = {**route, "role_mode_shadow": {"status": "selected", "selected_style_id": "ancient_scholar"}}
        before = deepcopy(state)
        shadow_env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "presentation_content_plan,role_narration",
        }
        with patch.dict(os.environ, shadow_env, clear=False):
            update = atomic_read_plan_shadow_node(state, {"configurable": {"thread_id": "route-role"}})
        record = update["route_role_narration_evaluations"][-1]
        self.assertEqual(record["scene_kind"], "route_planning")
        self.assertEqual(record["role_mode"], "ancient_scholar")
        self.assertEqual(record["validation_status"], "accepted")
        self.assertTrue(record["legacy_message_preserved"])
        self.assertTrue(record["candidate_is_non_authoritative"])
        self.assertFalse(record["active_takeover"])
        self.assertEqual(record["state_writes"], [])
        self.assertEqual(state, before)

    def test_opening_shadow_is_independent_and_preserves_legacy_output(self):
        route = direct_route_node({
            "messages": [HumanMessage(content="选择经典模式，30分钟路线")],
            "visitor_profile": {
                "available_minutes": 30, "interests": [],
                "detail_level": "standard", "route_constraint": None,
            },
        })
        arrival_input = {**route, "messages": [HumanMessage(content="我到前院中部了")],
            "role_mode_shadow": {"status": "selected", "selected_style_id": "child"}}
        arrived = tour_event_node(arrival_input)
        state = {**arrival_input, **arrived}
        shadow_env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "presentation_content_plan,role_narration",
        }
        with patch.dict(os.environ, {"CJC_READ_ONLY_ROLLOUT_MODE": "off"}, clear=False):
            legacy = tour_opening_node(deepcopy(state))
        with patch.dict(os.environ, shadow_env, clear=False):
            update = tour_opening_node(state, {"configurable": {"thread_id": "opening-role"}})
        self.assertEqual(update["messages"][0].content, legacy["messages"][0].content)
        record = update["route_role_narration_evaluations"][-1]
        self.assertEqual(record["scene_kind"], "route_opening")
        self.assertEqual(record["role_mode"], "child")
        self.assertEqual(record["validation_status"], "accepted")
        self.assertEqual(record["fact_diff"], [])
        self.assertEqual(record["route_diff"], [])
        self.assertEqual(record["safety_diff"], [])


if __name__ == "__main__":
    unittest.main()
