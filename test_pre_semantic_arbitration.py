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

    def test_explicit_duration_is_owned_before_semantic_model(self):
        for text in ("1.5个小时", "1.5小时", "一个半小时", "90分钟", "我有1.5个小时", "我还剩1.5小时"):
            with self.subTest(text=text):
                result = resolve_pre_semantic_action({}, text)
                self.assertTrue(result.consumed)
                self.assertEqual(result.route_target, "duration_control")
                self.assertFalse(result.model_required)

    def test_duration_questions_and_vague_time_are_not_claimed(self):
        for text in ("闭馆前1.5小时能进入吗？", "这个故事讲了1.5小时吗？", "时间不多"):
            with self.subTest(text=text):
                result = resolve_pre_semantic_action({}, text)
                self.assertFalse(result.consumed)

    def test_arrival_shaped_but_unsafe_text_is_consumed_as_clarification(self):
        """Arrival control may never use semantic-model failure as a RAG fallback."""
        for text in (
            "我还没抵达月台。",
            "我人还在路上。",
            "我准备去月台。",
            "我快走到月台了。",
            "如果到了月台。",
            "我是不是到月台了？",
            "朋友已经抵达月台。",
            "我刚抵达那边。",
        ):
            with self.subTest(text=text):
                result = resolve_pre_semantic_action({}, text)
                self.assertTrue(result.consumed)
                self.assertEqual(result.route_target, "clarification")
                self.assertFalse(result.model_required)

    def test_stop_completion_controls_are_consumed_before_semantic_model(self):
        for text in (
            "完成本点", "确认完成本点", "本点完成", "完成这个点", "这个点完成了",
            "这站完成了", "这一站参观完了", "这个点看完了", "这里看完了",
            "我看完这个点了", "本点已经参观完成", "可以去下一站了",
            "还没完成本点", "不要完成本点", "完成本点是什么意思？", "完成后会去哪？",
        ):
            with self.subTest(text=text):
                result = resolve_pre_semantic_action({}, text)
                self.assertTrue(result.consumed)
                self.assertFalse(result.model_required)


if __name__ == "__main__":
    unittest.main()
