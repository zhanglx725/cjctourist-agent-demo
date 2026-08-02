from __future__ import annotations
import unittest
from state_transition_adapter import ConfirmedEvent, apply_confirmed_event
class StateTransitionAdapterTests(unittest.TestCase):
 def test_requires_confirmation_and_valid_event(self):
  self.assertEqual(apply_confirmed_event(ConfirmedEvent("next_stop",{},False),{},{}).reason,"confirmation_required")
  self.assertEqual(apply_confirmed_event(ConfirmedEvent("invent",{},True),{},{}).reason,"invalid_event")
 def test_delegates_once_with_copied_inputs(self):
  state={"a":{"x":1}}; seen=[]
  def handler(s,i,event,**p): seen.append((s,i,event,p)); s["a"]["x"]=2; return {"ok":True}
  result=apply_confirmed_event(ConfirmedEvent("next_stop",{"x":1},True),state,{},handler=handler)
  self.assertTrue(result.applied); self.assertEqual(len(seen),1); self.assertEqual(state,{"a":{"x":1}})
if __name__=="__main__": unittest.main()
