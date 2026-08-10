from __future__ import annotations
from copy import deepcopy
from unittest.mock import patch
import unittest

from agent_graph import replan_proposal_shadow_node


class ReplanProposalShadowTests(unittest.TestCase):
 def setUp(self):
  self.tour={"current_stop_id":"platform","visited_stop_ids":["gate"],"skipped_stop_ids":["side"],"selected_route_id":"legacy"}
  self.proposal={"schema_version":"p1-11","origin_node_id":"platform","physical_node_snapshot":"platform","route_id":"legacy","remaining_minutes":40,"guide_stop_ids":["platform","hall"],"visited_stop_ids_snapshot":["gate"],"skipped_stop_ids_snapshot":["side"],"status":"awaiting_route_confirmation","pending_action_kind":"replan_route_confirmation"}
  self.state={"tour_state":deepcopy(self.tour),"pending_replan_proposal":deepcopy(self.proposal),"replan_proposal_evaluations":[]}
  self.env={"CJC_READ_ONLY_ROLLOUT_MODE":"shadow","CJC_READ_ONLY_ROLLOUT_CAPABILITIES":"replan_proposal"}

 def test_wraps_the_same_legacy_preview_without_formal_state_mutation(self):
  before=deepcopy(self.state)
  with patch.dict("os.environ",self.env,clear=False): result=replan_proposal_shadow_node(self.state,{"configurable":{"thread_id":"one"}})
  record=result["replan_proposal_evaluations"][0]
  self.assertEqual(self.state,before); self.assertEqual(record["proposal"],self.proposal)
  self.assertEqual(record["validation_status"],"accepted"); self.assertTrue(record["matches_legacy"])
  self.assertEqual(record["origin_node"],"platform"); self.assertEqual(record["candidate_stop_ids"],["platform","hall"])

 def test_stale_snapshot_is_rejected_without_default_proposal(self):
  self.state["tour_state"]["current_stop_id"]="courtyard"
  with patch.dict("os.environ",self.env,clear=False): result=replan_proposal_shadow_node(self.state,{"configurable":{"thread_id":"one"}})
  record=result["replan_proposal_evaluations"][0]
  self.assertEqual((record["validation_status"],record["rejected_reason"],record["proposal"]),("rejected","origin_snapshot_stale",None))

 def test_disabled_shadow_writes_nothing(self):
  with patch.dict("os.environ",{"CJC_READ_ONLY_ROLLOUT_MODE":"off","CJC_READ_ONLY_ROLLOUT_CAPABILITIES":"replan_proposal"},clear=False): self.assertEqual(replan_proposal_shadow_node(self.state,{}),{})

 def test_shadow_mode_reports_a_capability_configuration_mismatch(self):
  env={"CJC_READ_ONLY_ROLLOUT_MODE":"shadow","CJC_READ_ONLY_ROLLOUT_CAPABILITIES":"atomic_read_plan"}
  with patch.dict("os.environ",env,clear=False): result=replan_proposal_shadow_node(self.state,{"configurable":{"thread_id":"one"}})
  record=result["replan_proposal_evaluations"][0]
  self.assertEqual((record["validation_status"],record["rejected_reason"],record["proposal"]),("rejected","capability_not_enabled",None))
  self.assertEqual(record["runtime_capabilities"],["atomic_read_plan"])

 def test_shadow_never_calls_replanner_or_state_adapter(self):
  with patch.dict("os.environ",self.env,clear=False), patch("agent_graph.prepare_remaining_route_proposal") as replan, patch("agent_graph.handle_tour_event") as transition:
   replan_proposal_shadow_node(self.state,{"configurable":{"thread_id":"one"}})
  replan.assert_not_called(); transition.assert_not_called()

 def test_thread_audit_records_do_not_cross(self):
  with patch.dict("os.environ",self.env,clear=False):
   first=replan_proposal_shadow_node(self.state,{"configurable":{"thread_id":"one"}})
   second=replan_proposal_shadow_node({**self.state,"replan_proposal_evaluations":[]},{"configurable":{"thread_id":"two"}})
  self.assertEqual(first["replan_proposal_evaluations"][0]["thread_id"],"one")
  self.assertEqual(second["replan_proposal_evaluations"][0]["thread_id"],"two")


if __name__=="__main__": unittest.main()
