from __future__ import annotations
from copy import deepcopy
import unittest
from replan_proposal import propose_remaining_route
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
if __name__=="__main__": unittest.main()
