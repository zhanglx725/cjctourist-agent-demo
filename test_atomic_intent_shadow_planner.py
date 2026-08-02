from __future__ import annotations

import unittest

from atomic_intent_shadow_planner import observe_atomic_read_intents
from tool_registry import RuntimePhase


class AtomicIntentShadowPlannerTests(unittest.TestCase):
    def test_two_distinct_read_capabilities_form_an_audit_only_atomic_plan(self):
        result = observe_atomic_read_intents(
            "陈家祠什么时候开始筹建，再团队订单电子发票规则是什么？",
            phase=RuntimePhase.PRE_TOUR,
        )
        self.assertEqual(result.decision_kind, "atomic_read_plan")
        self.assertEqual([item["requested_capability"] for item in result.candidates], ["single_fact", "controlled_knowledge"])
        self.assertNotIn("tool_name", str(result.audit_dict()))

    def test_control_or_route_combinations_only_record_clarification(self):
        for text in (
            "先告诉我灰塑是什么，再继续带我走。",
            "我到月台了，先讲讲石雕，再告诉我下一站。",
            "我到月台了，顺便讲讲石雕，再重新规划。",
        ):
            with self.subTest(text=text):
                result = observe_atomic_read_intents(text, phase=RuntimePhase.TOURING)
                self.assertEqual(result.decision_kind, "clarification")
                self.assertIn("state_or_route_action", result.reason_codes)

    def test_single_unknown_and_empty_input_do_not_form_a_plan(self):
        self.assertEqual(observe_atomic_read_intents("陈家祠是什么？", phase=RuntimePhase.PRE_TOUR).decision_kind, "not_multi_intent")
        self.assertEqual(observe_atomic_read_intents("", phase=RuntimePhase.PRE_TOUR).decision_kind, "clarification")


if __name__ == "__main__":
    unittest.main()
