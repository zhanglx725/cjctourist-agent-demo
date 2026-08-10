"""CA-05 shadow observations cannot alter the legacy execution path."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from shadow_planner import ShadowMode, ShadowPlannerConfig, observe_shadow_plan


USER = "陈家祠什么时候开始筹建？"
CANDIDATE = {
    "intent": "fact_question", "sub_intents": [], "requested_capability": "single_fact",
    "target_text": USER, "evidence_span": USER, "confidence": 0.95,
    "requires_clarification": False, "requires_confirmation": False,
    "side_effect_level": "read_only",
}


class ShadowPlannerTests(unittest.TestCase):
    def test_off_is_default_and_never_invokes_a_model(self):
        result = observe_shadow_plan(USER, {"capability": "single_fact"}, lambda _: self.fail("off must not invoke"))
        self.assertEqual(result.status, "off")
        self.assertIsNone(result.candidate)

    def test_shadow_observes_one_valid_candidate_without_mutating_legacy_path(self):
        legacy = {"capability": "single_fact", "route": "tour_qa", "state": {"current_stop_id": "x"}}
        before, calls = deepcopy(legacy), []
        result = observe_shadow_plan(USER, legacy, lambda prompt: calls.append(prompt) or json.dumps(CANDIDATE, ensure_ascii=False), config=ShadowPlannerConfig(mode=ShadowMode.SHADOW))
        self.assertEqual(result.status, "observed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(legacy, before)
        self.assertTrue(result.capability_matches_legacy)
        self.assertTrue(result.candidate["decision_id"].startswith("dec_"))
        self.assertNotIn("只读影子规划器", str(result.audit_dict()))

    def test_invalid_candidate_and_model_failure_fall_back_without_execution(self):
        config = ShadowPlannerConfig(mode=ShadowMode.SHADOW)
        invalid = observe_shadow_plan(USER, {"route": "tour_qa"}, lambda _: "not json", config=config)
        unavailable = observe_shadow_plan(USER, {"route": "tour_qa"}, lambda _: (_ for _ in ()).throw(RuntimeError("down")), config=config)
        self.assertEqual((invalid.status, invalid.validation_code), ("candidate_rejected", "invalid_json"))
        self.assertEqual((unavailable.status, unavailable.validation_code), ("model_unavailable", "model_unavailable"))

    def test_limits_and_unregistered_model_fields_fail_closed(self):
        with self.assertRaises(ValueError):
            ShadowPlannerConfig(mode=ShadowMode.SHADOW, max_candidates_per_turn=2)
        candidate = dict(CANDIDATE, node_id="forged")
        result = observe_shadow_plan(USER, {}, lambda _: candidate, config=ShadowPlannerConfig(mode=ShadowMode.SHADOW))
        self.assertEqual(result.status, "candidate_rejected")
        self.assertEqual(result.validation_code, "schema_keys_rejected")


if __name__ == "__main__":
    unittest.main()
