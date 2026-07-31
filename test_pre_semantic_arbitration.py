"""Contract tests for the read-only deterministic semantic gate."""

from __future__ import annotations

import copy
import unittest

from pre_semantic_arbitration import resolve_pre_semantic_action


class PreSemanticArbitrationTests(unittest.TestCase):
    def test_pending_action_wins_without_mutating_input(self):
        state = {
            "pending_replan_proposal": {"status": "awaiting_route_confirmation"},
            "tour_state": {"current_stop_id": "stop_rear_courtyard"},
            "visitor_profile": {"interests": ["灰塑"]},
        }
        before = copy.deepcopy(state)
        result = resolve_pre_semantic_action(state, "确认新路线")
        self.assertTrue(result.consumed)
        self.assertEqual(result.reason, "pending_replan_confirmation")
        self.assertFalse(result.model_required)
        self.assertEqual(state, before)

    def test_specialist_and_fact_channels_precede_broad_model(self):
        self.assertEqual(
            resolve_pre_semantic_action({}, "石雕是什么？").reason,
            "specialist_channel",
        )
        self.assertEqual(
            resolve_pre_semantic_action({}, "陈家祠地址在哪里？").reason,
            "deterministic_fact",
        )
        self.assertEqual(
            resolve_pre_semantic_action({}, "我到月台了").reason,
            "deterministic_event_or_control",
        )

    def test_unconsumed_text_is_the_only_case_that_can_request_model(self):
        result = resolve_pre_semantic_action({}, "给我排一条不绕路的线路")
        self.assertFalse(result.consumed)
        self.assertTrue(result.model_required)


if __name__ == "__main__":
    unittest.main()
