from __future__ import annotations

from dataclasses import replace
import unittest

from agent_decision import SideEffectLevel, validate_agent_decision
from policy_gate import evaluate_policy
from tool_registry import RuntimePhase


TEXT = "陈家祠什么时候开始筹建？"
PAYLOAD = {"intent":"fact_question","sub_intents":[],"requested_capability":"single_fact","target_text":TEXT,"evidence_span":TEXT,"confidence":0.95,"requires_clarification":False,"requires_confirmation":False,"side_effect_level":"read_only"}


class PolicyGateTests(unittest.TestCase):
    def setUp(self): self.valid = validate_agent_decision(PAYLOAD, user_text=TEXT)
    def test_registered_read_only_candidate_needs_all_evidence_claims(self):
        self.assertEqual(evaluate_policy(self.valid, phase=RuntimePhase.PRE_TOUR).reason, "evidence_missing")
        result = evaluate_policy(self.valid, phase=RuntimePhase.PRE_TOUR, evidence_claims=("reviewed_category", "registered_source"))
        self.assertTrue(result.approved); self.assertEqual(result.tool_name, "reviewed_single_fact")
    def test_invalid_unregistered_and_side_effect_candidates_fail_closed(self):
        self.assertFalse(evaluate_policy(validate_agent_decision("bad", user_text=TEXT), phase=RuntimePhase.PRE_TOUR).approved)
        changed = replace(self.valid.decision, side_effect_level=SideEffectLevel.PROPOSAL)
        self.assertEqual(evaluate_policy(replace(self.valid, decision=changed), phase=RuntimePhase.TOURING).reason, "side_effect_rejected")
        route = dict(PAYLOAD, intent="route_planning", requested_capability="route_proposal", side_effect_level="proposal")
        self.assertEqual(evaluate_policy(validate_agent_decision(route, user_text=TEXT), phase=RuntimePhase.PRE_TOUR).reason, "side_effect_rejected")
    def test_phase_and_confirmation_are_checked_before_execution(self):
        changed = replace(self.valid.decision, requires_confirmation=True)
        self.assertEqual(evaluate_policy(replace(self.valid, decision=changed), phase=RuntimePhase.TOURING).reason, "confirmation_required")

if __name__ == "__main__": unittest.main()
