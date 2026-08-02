from __future__ import annotations
import unittest
from route_proposal import propose_reviewed_route
from route_planner import RoutePlanningError
class RouteProposalTests(unittest.TestCase):
 def test_only_approved_budgeted_plan_becomes_confirmation_proposal(self):
  result=propose_reviewed_route("highlights_30")
  self.assertEqual(result.status,"proposed"); self.assertTrue(result.requires_confirmation); self.assertIn("确认前",result.message)
 def test_planner_failure_closes_without_route_application(self):
  result=propose_reviewed_route("bad",planner=lambda _: (_ for _ in ()).throw(RoutePlanningError("bad")))
  self.assertEqual((result.status,result.proposal,result.requires_confirmation),("unavailable",None,False))
if __name__=="__main__": unittest.main()
