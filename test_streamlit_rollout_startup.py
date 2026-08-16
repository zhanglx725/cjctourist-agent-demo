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
        "route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail"
    ),
    "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "100",
    "PRODUCT_ROLE_KILL_SWITCH": "false",
    "PRODUCT_ROLE_VALIDATION_LEVEL": "strict",
    "PRODUCT_ROLE_FALLBACK_POLICY": "legacy",
}


class StreamlitRolloutStartupTests(unittest.TestCase):
    def test_ui_exposes_all_reviewed_styles(self):
        self.assertEqual(len(streamlit_app.STYLES), 18)
        self.assertEqual(
            set(streamlit_app.STYLES.values()),
            set(STOP_GUIDANCE_ACTIVE_STYLES),
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
        rendered = repr(audit)
        self.assertNotIn("must-not-appear", rendered)
        self.assertNotIn("API_KEY", rendered)


if __name__ == "__main__":
    unittest.main()
