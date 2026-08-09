from __future__ import annotations

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent_graph import (
    _competition_stop_guidance_style,
    _route_role_narration_shadow_update,
)
from controlled_rollout import (
    competition_role_active_allowed,
    competition_role_active_from_environment,
)
from presentation_content_plan import build_presentation_content_plan


ACTIVE_ENV = {
    "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
    "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
    "ROLE_ACTIVE_ENABLED": "true",
    "ROLE_ACTIVE_STYLES": "neutral,child,ancient_scholar",
    "ROLE_ACTIVE_SCENES": "route_planning,route_opening,stop_guidance",
}

SOURCES = {
    "route_planning": (
        "visitor_profile", "guidance_policy", "route_selection", "route_stop_catalog",
    ),
    "route_opening": (
        "route_selection", "route_stop_catalog", "tour_opening_evidence",
    ),
    "navigation": ("tour_state", "approved_spatial_graph", "route_stop_catalog"),
}


def _plan(scene_kind: str, role_mode: str) -> dict:
    return build_presentation_content_plan(
        scene_kind=scene_kind,
        role_mode=role_mode,
        detail_level="standard",
        budget_seconds=600,
        source_of_facts=SOURCES[scene_kind],
    ).to_dict()


def _state(legacy_text: str = "Reviewed route. First stop: front courtyard.") -> dict:
    return {
        "messages": [AIMessage(id="legacy-route", content=legacy_text)],
        "route_role_narration_evaluations": [],
    }


class CompetitionRoleActiveTests(unittest.TestCase):
    def test_conflicting_or_unknown_role_never_becomes_neutral_active(self):
        self.assertEqual(_competition_stop_guidance_style(None), "neutral")
        self.assertEqual(
            _competition_stop_guidance_style({"status": "not_requested"}),
            "neutral",
        )
        self.assertEqual(
            _competition_stop_guidance_style({
                "status": "selected", "selected_style_id": "child",
            }),
            "child",
        )
        for role_mode in (
            {"status": "clarification", "selected_style_id": None},
            {"status": "rejected", "selected_style_id": "neutral"},
            {"status": "selected", "selected_style_id": "unknown"},
        ):
            with self.subTest(role_mode=role_mode):
                self.assertIsNone(_competition_stop_guidance_style(role_mode))

    def test_policy_defaults_off_and_requires_both_rollout_layers(self):
        self.assertFalse(competition_role_active_from_environment({}).enabled)
        self.assertFalse(competition_role_active_allowed(
            "ancient_scholar", "route_planning", {},
        ))
        missing_generic = {
            **ACTIVE_ENV,
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
        }
        self.assertFalse(competition_role_active_allowed(
            "ancient_scholar", "route_planning", missing_generic,
        ))

    def test_fixed_pair_allowlist_rejects_unapproved_combinations(self):
        self.assertTrue(competition_role_active_allowed(
            "ancient_scholar", "route_planning", ACTIVE_ENV,
        ))
        self.assertTrue(competition_role_active_allowed(
            "ancient_scholar", "route_opening", ACTIVE_ENV,
        ))
        self.assertTrue(competition_role_active_allowed(
            "child", "stop_guidance", ACTIVE_ENV,
        ))
        self.assertTrue(competition_role_active_allowed(
            "neutral", "stop_guidance", ACTIVE_ENV,
        ))
        self.assertTrue(competition_role_active_allowed(
            "ancient_scholar", "stop_guidance", ACTIVE_ENV,
        ))
        for style_id, scene_kind in (
            ("child", "route_planning"),
            ("neutral", "route_opening"),
            ("ancient_scholar", "navigation"),
            ("child", "tour_qa"),
            ("professional", "qa_follow_up_detail"),
            ("dominant_ceo", "stop_guidance"),
        ):
            with self.subTest(style_id=style_id, scene_kind=scene_kind):
                self.assertFalse(competition_role_active_allowed(
                    style_id, scene_kind, ACTIVE_ENV,
                ))

    def test_ancient_scholar_route_planning_and_opening_take_over(self):
        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            for scene_kind in ("route_planning", "route_opening"):
                with self.subTest(scene_kind=scene_kind):
                    state = _state()
                    update = _route_role_narration_shadow_update(
                        state,
                        {"configurable": {"thread_id": f"active-{scene_kind}"}},
                        presentation_plan=_plan(scene_kind, "ancient_scholar"),
                    )
                    audit = update["route_role_narration_evaluations"][-1]
                    self.assertEqual(audit["validation_status"], "accepted")
                    self.assertTrue(audit["active_takeover"])
                    self.assertFalse(audit["fallback_used"])
                    self.assertFalse(audit["legacy_message_preserved"])
                    self.assertTrue(audit["same_fact_boundary"])
                    self.assertTrue(audit["public_message_safe"])
                    self.assertTrue(audit["within_budget"])
                    self.assertEqual(audit["state_writes"], [])
                    self.assertEqual(update["messages"][0].id, "legacy-route")
                    self.assertIn(state["messages"][0].content, update["messages"][0].content)

    def test_route_active_audit_does_not_mutate_authoritative_state_or_other_thread(self):
        authoritative = {
            "tour_state": {"current_stop_id": "stop_a", "visited_stop_ids": []},
            "visitor_profile": {"style_id": "ancient_scholar"},
            "active_route_plan": {"route_stop_ids": ["stop_a", "stop_b"]},
            "pending_replan_proposal": {"status": "none"},
            "active_stop_program": {"stop_id": "stop_a"},
        }
        first = {**_state(), **deepcopy(authoritative)}
        second = {**_state(), **deepcopy(authoritative)}

        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            update = _route_role_narration_shadow_update(
                first,
                {"configurable": {"thread_id": "competition-thread-a"}},
                presentation_plan=_plan("route_planning", "ancient_scholar"),
            )

        for key, value in authoritative.items():
            self.assertNotIn(key, update)
            self.assertEqual(first[key], value)
            self.assertEqual(second[key], value)
        self.assertEqual(second["route_role_narration_evaluations"], [])

    def test_unapproved_scene_or_style_stays_shadow_and_preserves_message(self):
        with patch.dict(os.environ, ACTIVE_ENV, clear=False):
            for scene_kind, role_mode in (
                ("route_planning", "child"),
                ("navigation", "ancient_scholar"),
            ):
                with self.subTest(scene_kind=scene_kind, role_mode=role_mode):
                    update = _route_role_narration_shadow_update(
                        _state(), None,
                        presentation_plan=_plan(scene_kind, role_mode),
                    )
                    audit = update["route_role_narration_evaluations"][-1]
                    self.assertFalse(audit["active_takeover"])
                    self.assertTrue(audit["legacy_message_preserved"])
                    self.assertNotIn("messages", update)

    def test_active_route_validation_failure_falls_back_to_legacy(self):
        invalid_candidate = {
            "schema_version": "route_role_text_candidate_v1",
            "scene_kind": "route_planning",
            "role_mode": "ancient_scholar",
            "public_text": "source_ids=S01",
        }
        with patch.dict(os.environ, ACTIVE_ENV, clear=False), patch(
            "agent_graph.build_route_role_text_candidate",
            return_value=invalid_candidate,
        ):
            update = _route_role_narration_shadow_update(
                _state(), None,
                presentation_plan=_plan("route_planning", "ancient_scholar"),
            )
        audit = update["route_role_narration_evaluations"][-1]
        self.assertEqual(audit["validation_status"], "rejected")
        self.assertFalse(audit["active_takeover"])
        self.assertTrue(audit["fallback_used"])
        self.assertTrue(audit["legacy_message_preserved"])
        self.assertIn("internal_field_leak", audit["reason_codes"])
        self.assertNotIn("messages", update)

    def test_kill_switch_keeps_legacy_message(self):
        disabled = {**ACTIVE_ENV, "ROLE_ACTIVE_ENABLED": "false"}
        with patch.dict(os.environ, disabled, clear=False):
            update = _route_role_narration_shadow_update(
                _state(), None,
                presentation_plan=_plan("route_planning", "ancient_scholar"),
            )
        audit = update["route_role_narration_evaluations"][-1]
        self.assertFalse(audit["active_takeover"])
        self.assertTrue(audit["legacy_message_preserved"])
        self.assertNotIn("messages", update)


if __name__ == "__main__":
    unittest.main()
