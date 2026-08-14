from __future__ import annotations

import unittest

from tools.aggregate_role_narration_langsmith_evaluation import _unique


class AggregateRoleNarrationLangSmithEvaluationTests(unittest.TestCase):
    def test_duplicate_case_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate base"):
            _unique([{"case_id": "same"}, {"case_id": "same"}], "base")

    def test_unique_case_ids_are_preserved(self):
        records = [{"case_id": "one"}, {"case_id": "two"}]
        self.assertEqual(_unique(records, "base"), records)


if __name__ == "__main__":
    unittest.main()
