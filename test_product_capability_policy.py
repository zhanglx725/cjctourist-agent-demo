"""Product role rollout policy: strict parsing, compatibility and stability."""

from __future__ import annotations

import unittest

from controlled_rollout import (
    ProductCapabilityPolicy,
    ProductScenePolicy,
    ProductStylePolicy,
    product_capability_policy_from_environment,
    product_role_active_allowed,
)


MATURE_ROLLOUT = {
    "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
    "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
}
PRODUCT_POLICY = {
    **MATURE_ROLLOUT,
    "PRODUCT_ROLE_ACTIVE_ENABLED": "true",
    "PRODUCT_ROLE_ACTIVE_STYLES": "ancient_scholar,child",
    "PRODUCT_ROLE_ACTIVE_SCENES": "stop_guidance,tour_qa,navigation",
    "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "100",
    "PRODUCT_ROLE_KILL_SWITCH": "false",
    "PRODUCT_ROLE_VALIDATION_LEVEL": "strict",
    "PRODUCT_ROLE_FALLBACK_POLICY": "legacy",
}


class ProductCapabilityPolicyTests(unittest.TestCase):
    def test_default_is_disabled_and_auditable(self):
        policy = product_capability_policy_from_environment({})
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.reason_code, "legacy_policy_disabled")
        self.assertEqual(policy.to_audit()["source"], "disabled")

    def test_product_policy_builds_scene_and_style_contracts(self):
        policy = product_capability_policy_from_environment(PRODUCT_POLICY)
        self.assertTrue(policy.enabled)
        self.assertIsInstance(policy.scene_policies[0], ProductScenePolicy)
        self.assertIsInstance(policy.scene_policies[0].styles[0], ProductStylePolicy)
        self.assertTrue(policy.allows("ancient_scholar", "tour_qa"))
        self.assertFalse(policy.allows("family", "tour_qa"))

    def test_legacy_configuration_remains_supported_only_when_product_is_absent(self):
        legacy = {
            **MATURE_ROLLOUT,
            "ROLE_ACTIVE_ENABLED": "true",
            "ROLE_ACTIVE_STYLES": "ancient_scholar",
            "ROLE_ACTIVE_SCENES": "stop_guidance",
        }
        policy = product_capability_policy_from_environment(legacy)
        self.assertEqual(policy.source, "legacy_compatibility")
        self.assertTrue(product_role_active_allowed(
            "ancient_scholar", "stop_guidance", legacy,
        ))

        partial_product = {**legacy, "PRODUCT_ROLE_ACTIVE_ENABLED": "true"}
        policy = product_capability_policy_from_environment(partial_product)
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.reason_code, "incomplete_product_policy")

    def test_invalid_or_unknown_values_fail_closed(self):
        cases = [
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_ACTIVE_ENABLED": "yes"},
             "invalid_product_policy_boolean"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "101"},
             "invalid_product_policy_values"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "many"},
             "invalid_rollout_percentage"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_VALIDATION_LEVEL": "relaxed"},
             "invalid_product_policy_values"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_FALLBACK_POLICY": "none"},
             "invalid_product_policy_values"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_ACTIVE_STYLES": "unknown"},
             "unknown_product_policy_target"),
            ({**PRODUCT_POLICY, "PRODUCT_ROLE_ACTIVE_SCENES": "unknown"},
             "unknown_product_policy_target"),
        ]
        for environment, reason_code in cases:
            with self.subTest(reason_code=reason_code):
                policy = product_capability_policy_from_environment(environment)
                self.assertFalse(policy.enabled)
                self.assertEqual(policy.reason_code, reason_code)

    def test_kill_switch_and_mature_rollout_are_both_required(self):
        killed = {**PRODUCT_POLICY, "PRODUCT_ROLE_KILL_SWITCH": "true"}
        self.assertFalse(product_role_active_allowed(
            "ancient_scholar", "stop_guidance", killed,
        ))
        rollout_off = {**PRODUCT_POLICY, "CJC_READ_ONLY_ROLLOUT_MODE": "off"}
        self.assertFalse(product_role_active_allowed(
            "ancient_scholar", "stop_guidance", rollout_off,
        ))

    def test_percentage_rollout_is_thread_stable_and_missing_thread_fails_closed(self):
        partial = {**PRODUCT_POLICY, "PRODUCT_ROLE_ROLLOUT_PERCENTAGE": "37"}
        self.assertFalse(product_role_active_allowed(
            "ancient_scholar", "stop_guidance", partial,
        ))
        first = product_role_active_allowed(
            "ancient_scholar", "stop_guidance", partial, thread_id="visitor-42",
        )
        for _ in range(10):
            self.assertEqual(first, product_role_active_allowed(
                "ancient_scholar", "stop_guidance", partial,
                thread_id="visitor-42",
            ))

    def test_zero_and_full_rollout_have_explicit_boundaries(self):
        zero = ProductCapabilityPolicy(
            enabled=True, styles=frozenset({"child"}),
            scenes=frozenset({"stop_guidance"}), rollout_percentage=0,
        )
        full = ProductCapabilityPolicy(
            enabled=True, styles=frozenset({"child"}),
            scenes=frozenset({"stop_guidance"}), rollout_percentage=100,
        )
        self.assertFalse(zero.allows("child", "stop_guidance", thread_id="a"))
        self.assertTrue(full.allows("child", "stop_guidance"))


if __name__ == "__main__":
    unittest.main()
