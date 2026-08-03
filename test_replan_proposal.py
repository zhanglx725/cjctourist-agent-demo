from __future__ import annotations
from copy import deepcopy
import unittest
from replan_proposal import propose_remaining_route, wrap_existing_replan_proposal_for_shadow
class ReplanProposalTests(unittest.TestCase):
 def test_invalid_snapshot_fails_closed_without_mutation(self):
  state={"current_stop_id":"a"}; before=deepcopy(state)
  result=propose_remaining_route(state,origin_node_id="b",origin_source="visitor")
  self.assertEqual((result.status,result.proposal),("unavailable",None)); self.assertEqual(state,before)
 def test_preparer_receives_copy_and_result_stays_pending_confirmation(self):
  state={"x":1}
  class P:
   def to_dict(self): return {"origin_node_id":"a","status":"awaiting_route_confirmation"}
  def prepare(value,**_): value["x"]=2; return P()
  result=propose_remaining_route(state,origin_node_id="a",origin_source="visitor",preparer=prepare)
  self.assertEqual(result.status,"awaiting_confirmation"); self.assertEqual(state,{"x":1})
 def test_existing_legacy_proposal_is_wrapped_without_replanning(self):
  tour={"current_stop_id":"node_a","visited_stop_ids":["node_old"],"skipped_stop_ids":[]}
  proposal={"origin_node_id":"node_a","physical_node_snapshot":"node_a","route_id":"r","remaining_minutes":30,"guide_stop_ids":["node_a","node_b"],"visited_stop_ids_snapshot":["node_old"],"skipped_stop_ids_snapshot":[],"status":"awaiting_route_confirmation","pending_action_kind":"replan_route_confirmation"}
  result=wrap_existing_replan_proposal_for_shadow(proposal,tour)
  self.assertEqual(result.validation_status,"accepted"); self.assertEqual(result.proposal,proposal)
 def test_stale_snapshot_fails_closed(self):
  proposal={"origin_node_id":"a","physical_node_snapshot":"a","route_id":"r","remaining_minutes":30,"guide_stop_ids":["a"],"visited_stop_ids_snapshot":[],"skipped_stop_ids_snapshot":[],"status":"awaiting_route_confirmation","pending_action_kind":"replan_route_confirmation"}
  self.assertEqual(wrap_existing_replan_proposal_for_shadow(proposal,{"current_stop_id":"b","visited_stop_ids":[],"skipped_stop_ids":[]}).rejected_reason,"origin_snapshot_stale")
if __name__=="__main__": unittest.main()
