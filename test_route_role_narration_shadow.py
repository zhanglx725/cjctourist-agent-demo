from __future__ import annotations

import os
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    atomic_read_plan_shadow_node,
    direct_route_node,
    post_visit_title_blessing_node,
    tour_event_node,
    tour_opening_node,
    visit_summary_node,
)
from narration_coverage import empty_narration_coverage
from presentation_content_plan import build_presentation_content_plan
from route_role_narration_shadow import (
    build_route_role_text_candidate,
    generate_route_role_text_candidate,
    validate_route_role_text_candidate,
)
from tour_state import finish_tour


SOURCES = {
    "route_planning": ("visitor_profile", "guidance_policy", "route_selection", "route_stop_catalog"),
    "route_opening": ("route_selection", "route_stop_catalog", "tour_opening_evidence"),
    "navigation": ("tour_state", "approved_spatial_graph", "route_stop_catalog"),
    "tour_closing": ("visit_summary", "narration_coverage", "tour_state"),
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
    def test_model_route_candidate_can_add_role_paragraphs_without_changing_route_units(self):
        legacy = "总时长30分钟。第一站为前院中部。请以现场安排为准。"
        candidate = generate_route_role_text_candidate(
            scene_kind="route_planning", role_mode="bestie_chat", legacy_text=legacy,
            invoke_model=lambda _: json.dumps({
                "schema_version": "route_role_text_candidate_v1",
                "scene_kind": "route_planning", "role_mode": "bestie_chat",
                "public_text": (
                    "咱们先把这一程的重点理顺。\n\n[[ROUTE_000]]"
                    "\n\n接下来就顺着这条线慢慢逛。[[ROUTE_001]]\n\n[[ROUTE_002]]"
                ),
            }, ensure_ascii=False),
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertIn("咱们先把这一程的重点理顺", candidate["public_text"])
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("route_planning", "bestie_chat"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "accepted", result)
        self.assertFalse(result["legacy_message_preserved"])

    def test_all_reviewed_roles_generate_valid_candidates_for_all_surfaces(self):
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

    def test_ancient_route_planning_and_opening_have_distinct_role_lead_ins(self):
        legacy = "路线已确认。第一站为前院中部。"
        planning = build_route_role_text_candidate(
            scene_kind="route_planning", role_mode="ancient_scholar",
            legacy_text=legacy,
        )
        opening = build_route_role_text_candidate(
            scene_kind="route_opening", role_mode="ancient_scholar",
            legacy_text=legacy,
        )
        self.assertIn("一卷徐徐展开的图景", planning["public_text"])
        self.assertIn("从眼前第一站启程", opening["public_text"])
        self.assertNotEqual(planning["public_text"], opening["public_text"])
        self.assertTrue(planning["public_text"].endswith(legacy))
        self.assertTrue(opening["public_text"].endswith(legacy))

    def test_every_reviewed_style_has_a_distinct_safe_route_opening(self):
        legacy = "路线已确认。第一站为前院中部。"
        roles = (
            "neutral", "family", "student_research", "professional", "mixed_group",
            "dominant_ceo", "cute_junior", "warm_sister", "bestie_chat", "buddy_guide",
            "exploration_game", "photo_guide", "hostel_scholar", "xiguan_young_master",
            "cantonese_storyteller",
        )
        for role in roles:
            with self.subTest(role=role):
                candidate = build_route_role_text_candidate(
                    scene_kind="route_opening", role_mode=role, legacy_text=legacy,
                )
                result = validate_route_role_text_candidate(
                    candidate, plan=_plan("route_opening", role), legacy_text=legacy,
                )
                self.assertEqual(result["validation_status"], "accepted")
                self.assertNotEqual(candidate["public_text"], legacy)
                self.assertTrue(candidate["public_text"].endswith(legacy))

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

    def test_navigation_shadow_preserves_legacy_route_and_state(self):
        route = direct_route_node({
            "messages": [HumanMessage(content="选择经典模式，30分钟路线")],
            "visitor_profile": {
                "available_minutes": 30, "interests": [],
                "detail_level": "standard", "route_constraint": None,
            },
        })
        tour = deepcopy(route["tour_state"])
        tour["route_status"] = "touring"
        tour["current_stop_id"] = tour["route_stop_ids"][0]
        tour["remaining_stop_ids"] = list(tour["route_stop_ids"])
        interaction = deepcopy(route["tour_interaction_state"])
        interaction["pending_stop_id"] = tour["current_stop_id"]
        interaction["stop_phase"] = "explaining"
        state = {
            **route,
            "messages": [HumanMessage(content="完成本点")],
            "tour_state": tour,
            "tour_interaction_state": interaction,
            "role_mode_shadow": {
                "status": "selected", "selected_style_id": "ancient_scholar",
            },
        }
        event_update = tour_event_node(state)
        event_state = {**state, **event_update}
        before = deepcopy(event_state)
        shadow_env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "presentation_content_plan,role_narration",
        }
        with patch.dict(os.environ, shadow_env, clear=False):
            update = atomic_read_plan_shadow_node(
                event_state, {"configurable": {"thread_id": "navigation-role"}},
            )
        plan = update["presentation_content_plan"]
        record = update["route_role_narration_evaluations"][-1]
        self.assertEqual(plan["scene_kind"], "navigation")
        self.assertEqual(record["scene_kind"], "navigation")
        self.assertEqual(record["role_mode"], "ancient_scholar")
        self.assertEqual(record["validation_status"], "accepted")
        self.assertTrue(record["legacy_message_preserved"])
        self.assertEqual(record["fact_diff"], [])
        self.assertEqual(record["route_diff"], [])
        self.assertEqual(record["safety_diff"], [])
        self.assertEqual(record["state_writes"], [])
        self.assertEqual(event_state, before)

    def test_navigation_listen_only_adds_no_question_or_task(self):
        legacy = "沿廊道前往下一站，现场通行请以工作人员指引为准。"
        candidate = build_route_role_text_candidate(
            scene_kind="navigation", role_mode="listen_only", legacy_text=legacy,
        )
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("navigation", "listen_only"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "accepted")
        self.assertNotRegex(candidate["public_text"], r"[?？]|请你|请问|回答|任务|拍照")

    def test_navigation_candidate_cannot_change_path_time_or_safety_text(self):
        legacy = "向东步行约40秒前往后座，现场通行请以工作人员指引为准。"
        candidate = build_route_role_text_candidate(
            scene_kind="navigation", role_mode="child", legacy_text=legacy,
        )
        candidate["public_text"] = candidate["public_text"].replace("向东", "向西")
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("navigation", "child"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "rejected")
        self.assertIn("legacy_boundary_or_role_template_mismatch", result["reason_codes"])

    def test_tour_closing_shadow_preserves_award_summary_and_operational_state(self):
        route = direct_route_node({
            "messages": [HumanMessage(content="选择经典模式，30分钟路线")],
            "visitor_profile": {
                "available_minutes": 30, "interests": ["灰塑"],
                "detail_level": "standard", "route_constraint": None,
            },
        })
        completed = {
            **route,
            "tour_state": finish_tour(route["tour_state"]),
            "narration_coverage": empty_narration_coverage().to_dict(),
            "tour_question_log": [],
            "role_mode_shadow": {
                "status": "selected", "selected_style_id": "child",
            },
        }
        summarized = {**completed, **visit_summary_node(completed)}
        closing_state = {
            **summarized, **post_visit_title_blessing_node(summarized),
        }
        before = deepcopy(closing_state)
        shadow_env = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "presentation_content_plan,role_narration",
        }
        with patch.dict(os.environ, shadow_env, clear=False):
            update = atomic_read_plan_shadow_node(
                closing_state, {"configurable": {"thread_id": "closing-role"}},
            )
        plan = update["presentation_content_plan"]
        record = update["route_role_narration_evaluations"][-1]
        self.assertEqual(plan["scene_kind"], "tour_closing")
        self.assertEqual(record["scene_kind"], "tour_closing")
        self.assertEqual(record["role_mode"], "child")
        self.assertEqual(record["validation_status"], "accepted")
        self.assertTrue(record["legacy_message_preserved"])
        self.assertEqual(record["fact_diff"], [])
        self.assertEqual(record["route_diff"], [])
        self.assertEqual(record["safety_diff"], [])
        self.assertEqual(record["state_writes"], [])
        self.assertEqual(closing_state, before)
        for field in (
            "tour_state", "visitor_profile", "narration_coverage",
            "visit_summary", "post_visit_award", "post_visit_nearby_offer",
        ):
            self.assertNotIn(field, update)

    def test_tour_closing_listen_only_does_not_reject_legacy_offer_question(self):
        legacy = (
            "你的本次游览称号是“百艺巡游者”。\n\n"
            "请问您是否需要我为您推荐一些周边的美食？"
        )
        candidate = build_route_role_text_candidate(
            scene_kind="tour_closing", role_mode="listen_only", legacy_text=legacy,
        )
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("tour_closing", "listen_only"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "accepted")

    def test_tour_closing_candidate_cannot_change_recorded_counts_or_title(self):
        legacy = "本次提出了 2 次问题。你的称号是“好奇探索者”。"
        candidate = build_route_role_text_candidate(
            scene_kind="tour_closing", role_mode="ancient_scholar", legacy_text=legacy,
        )
        candidate["public_text"] = candidate["public_text"].replace("2 次", "9 次")
        result = validate_route_role_text_candidate(
            candidate, plan=_plan("tour_closing", "ancient_scholar"), legacy_text=legacy,
        )
        self.assertEqual(result["validation_status"], "rejected")
        self.assertIn("legacy_boundary_or_role_template_mismatch", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
