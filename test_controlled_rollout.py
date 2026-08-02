import unittest
from controlled_rollout import ReadOnlyRollout,RolloutMode,evaluation_record
class T(unittest.TestCase):
 def test_modes_and_thread_records_are_isolated(self):
  self.assertFalse(ReadOnlyRollout().enabled("controlled_knowledge")); self.assertTrue(ReadOnlyRollout(RolloutMode.SHADOW).observes("controlled_knowledge")); self.assertTrue(ReadOnlyRollout(RolloutMode.READ_ONLY_ACTIVE).enabled("controlled_knowledge"))
  self.assertNotEqual(evaluation_record("a",{},{} )["thread_id"],evaluation_record("b",{},{} )["thread_id"])
if __name__=="__main__":unittest.main()
