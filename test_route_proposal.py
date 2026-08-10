from __future__ import annotations
import unittest
from route_proposal import propose_reviewed_route, wrap_route_selection_for_shadow
from route_planner import RoutePlanningError
from route_selection import recommend_route
class RouteProposalTests(unittest.TestCase):
 def test_only_approved_budgeted_plan_becomes_confirmation_proposal(self):
  result=propose_reviewed_route("highlights_30")
  self.assertEqual(result.status,"proposed"); self.assertTrue(result.requires_confirmation); self.assertIn("确认前",result.message)
 def test_planner_failure_closes_without_route_application(self):
  result=propose_reviewed_route("bad",planner=lambda _: (_ for _ in ()).throw(RoutePlanningError("bad")))
  self.assertEqual((result.status,result.proposal,result.requires_confirmation),("unavailable",None,False))
 def test_existing_anchor_selection_is_wrapped_without_replanning(self):
  selected=recommend_route(30,interests=["灰塑"],detail_level="standard").selected
  assert selected is not None
  audit=wrap_route_selection_for_shadow(selected,input_snapshot={"available_minutes":30},route_data_version={"catalog":"v1"})
  self.assertEqual(audit.validation_status,"accepted")
  assert audit.proposal is not None
  self.assertEqual(audit.proposal["selected_route_id"],selected.route_id)
  self.assertEqual(audit.proposal["guide_stop_ids"],list(selected.guide_stop_ids))
 def test_existing_dynamic_selection_is_wrapped_without_replanning(self):
  selected=recommend_route(60,interests=["灰塑","木雕"],detail_level="deep").selected
  assert selected is not None
  audit=wrap_route_selection_for_shadow(selected,input_snapshot={"available_minutes":60},route_data_version={"catalog":"v1"})
  self.assertEqual(audit.validation_status,"accepted")
  assert audit.proposal is not None
  self.assertEqual(audit.proposal["route_strategy"],selected.route_strategy)
if __name__=="__main__": unittest.main()
