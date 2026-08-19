from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from controlled_rollout import STOP_GUIDANCE_ACTIVE_STYLES
from demo import streamlit_app


ALL_STYLES = ",".join(sorted(STOP_GUIDANCE_ACTIVE_STYLES))
ACTIVE_ENV = {
    "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
    "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration,role_qa",
    "PRODUCT_ROLE_ACTIVE_ENABLED": "true",
    "PRODUCT_ROLE_ACTIVE_STYLES": ALL_STYLES,
    "PRODUCT_ROLE_ACTIVE_SCENES": (
        "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail,"
        "navigation,tour_closing,replan_presentation"
    ),
    "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "100",
    "PRODUCT_ROLE_KILL_SWITCH": "false",
    "PRODUCT_ROLE_VALIDATION_LEVEL": "strict",
    "PRODUCT_ROLE_FALLBACK_POLICY": "legacy",
    "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
}


class StreamlitRolloutStartupTests(unittest.TestCase):
    def test_ui_exposes_all_reviewed_styles(self):
        self.assertEqual(len(streamlit_app.STYLES), 18)
        self.assertEqual(
            set(streamlit_app.STYLES.values()),
            set(STOP_GUIDANCE_ACTIVE_STYLES),
        )

    def test_classic_route_request_needs_no_custom_preferences(self):
        self.assertEqual(
            streamlit_app._route_request_message("中文", "classic", duration=30),
            "中文，经典模式，30分钟",
        )

    def test_custom_route_request_contains_selected_crafts_and_style(self):
        self.assertEqual(
            streamlit_app._route_request_message(
                "英语",
                "custom",
                interests=["灰塑", "木雕"],
                style_label="古风书生",
                duration=30,
            ),
            "英语，定制模式，30分钟，我喜欢灰塑、木雕，选择古风书生风格",
        )

    def test_custom_route_request_rejects_missing_craft_preference(self):
        with self.assertRaises(ValueError):
            streamlit_app._route_request_message(
                "中文", "custom", interests=[], style_label="中性清晰",
            )

    def test_explicit_process_rollout_overrides_stale_streamlit_secrets(self):
        stale = {
            **ACTIVE_ENV,
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_qa",
            "PRODUCT_ROLE_ACTIVE_SCENES": "tour_qa,qa_follow_up_detail",
        }
        with patch.dict(os.environ, ACTIVE_ENV, clear=True), patch.object(
            streamlit_app.st, "secrets", stale,
        ):
            audit = streamlit_app._configure_environment()
            self.assertEqual(
                os.environ["CJC_READ_ONLY_ROLLOUT_CAPABILITIES"],
                "role_narration,role_qa",
            )
            self.assertIn("stop_guidance", os.environ["PRODUCT_ROLE_ACTIVE_SCENES"])
        self.assertTrue(audit["point_role_active_configured"])
        self.assertTrue(audit["qa_role_active_configured"])
        self.assertTrue(audit["natural_discourse_enabled"])

    def test_complete_deployment_secrets_fill_missing_runtime_settings(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            streamlit_app.st, "secrets", ACTIVE_ENV,
        ):
            audit = streamlit_app._configure_environment()
        self.assertEqual(audit["rollout_mode"], "read_only_active")
        self.assertEqual(set(audit["enabled_capabilities"]), {"role_narration", "role_qa"})
        self.assertEqual(len(audit["active_styles"]), 18)
        self.assertTrue(audit["point_role_active_configured"])
        self.assertTrue(audit["qa_role_active_configured"])
        self.assertTrue(audit["natural_discourse_enabled"])

    def test_incomplete_product_policy_fails_closed_and_audit_has_no_secrets(self):
        incomplete = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration,role_qa",
            "PRODUCT_ROLE_ACTIVE_ENABLED": "true",
            "DEEPSEEK_API_KEY": "must-not-appear",
            "LANGSMITH_API_KEY": "must-not-appear",
        }
        with patch.dict(os.environ, incomplete, clear=True), patch.object(
            streamlit_app.st, "secrets", {},
        ):
            audit = streamlit_app._configure_environment()
        self.assertFalse(audit["product_policy_enabled"])
        self.assertEqual(audit["product_policy_reason_code"], "incomplete_product_policy")
        self.assertFalse(audit["point_role_active_configured"])
        self.assertFalse(audit["qa_role_active_configured"])
        self.assertFalse(audit["natural_discourse_enabled"])
        rendered = repr(audit)
        self.assertNotIn("must-not-appear", rendered)
        self.assertNotIn("API_KEY", rendered)

    def test_runtime_fingerprint_changes_with_model_but_never_contains_a_secret(self):
        with patch.dict(os.environ, {**ACTIVE_ENV, "DEEPSEEK_API_KEY": "must-not-appear"}, clear=True):
            baseline = streamlit_app._role_rollout_startup_audit()
        with patch.dict(os.environ, {**ACTIVE_ENV, "DEEPSEEK_MODEL": "another-model"}, clear=True):
            changed_model = streamlit_app._role_rollout_startup_audit()
        self.assertNotEqual(baseline["runtime_fingerprint"], changed_model["runtime_fingerprint"])
        self.assertNotIn("must-not-appear", repr(baseline))


if __name__ == "__main__":
    unittest.main()
