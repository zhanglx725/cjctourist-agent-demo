from __future__ import annotations
from copy import deepcopy
import unittest
from agent_decision import validate_agent_decision
from atomic_read_plan import build_atomic_read_plan
from tool_registry import RuntimePhase

TEXT = "陈家祠什么时候开始筹建？"
def decision(cap="single_fact", intent="fact_question"):
 return validate_agent_decision({"intent":intent,"sub_intents":[],"requested_capability":cap,"target_text":TEXT,"evidence_span":TEXT,"confidence":.95,"requires_clarification":False,"requires_confirmation":False,"side_effect_level":"read_only"},user_text=TEXT)
class AtomicReadPlanTests(unittest.TestCase):
 def test_all_steps_are_approved_or_none_are_returned(self):
  result=build_atomic_read_plan([decision()],phase=RuntimePhase.PRE_TOUR,evidence_claims={"single_fact":("reviewed_category","registered_source")})
  self.assertTrue(result.accepted); self.assertEqual(len(result.plan.steps),1)
  failed=build_atomic_read_plan([decision()],phase=RuntimePhase.PRE_TOUR,evidence_claims={})
  self.assertEqual((failed.accepted,failed.plan,failed.reason),(False,None,"evidence_missing"))
 def test_duplicate_and_invalid_steps_fail_without_partial_plan(self):
  claims={"single_fact":("reviewed_category","registered_source")}
  self.assertEqual(build_atomic_read_plan([decision(),decision()],phase=RuntimePhase.TOURING,evidence_claims=claims).reason,"duplicate_capability")
  self.assertIsNone(build_atomic_read_plan([decision(),validate_agent_decision("bad",user_text=TEXT)],phase=RuntimePhase.TOURING,evidence_claims=claims).plan)
 def test_resume_snapshot_is_copied_not_recomputed_or_mutated(self):
  snapshot={"route_id":"r", "current_stop":"s"}; before=deepcopy(snapshot)
  result=build_atomic_read_plan([decision()],phase=RuntimePhase.TOURING,evidence_claims={"single_fact":("reviewed_category","registered_source")},resume_snapshot=snapshot)
  result.plan.resume_snapshot["route_id"]="changed"
  self.assertEqual(snapshot,before)
if __name__=="__main__": unittest.main()
