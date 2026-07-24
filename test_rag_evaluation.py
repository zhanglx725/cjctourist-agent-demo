"""Unit tests for evaluation matching, without loading models or indexes."""

import unittest

from rag_evaluation import RetrievalEvaluationCase, is_expected
from rag_retrieval import RetrievedEvidence


class RetrievalEvaluationTests(unittest.TestCase):
    def test_expected_match_requires_document_and_title(self):
        case = RetrievalEvaluationCase(
            "case", "问题", "02_history_architecture.md", ("建筑格局",), ("history_architecture",)
        )
        correct = RetrievedEvidence(
            "id", "text", 1.0, (), "02_history_architecture.md", ("历史", "建筑格局与参观亮点"),
            "history_architecture", ("S04",), None, None, None, None,
        )
        wrong = RetrievedEvidence(
            "id2", "text", 1.0, (), "07_ornament_crafts.md", ("工艺", "石雕"),
            "ornament_craft", ("S10",), None, None, None, None,
        )
        self.assertTrue(is_expected(case, correct))
        self.assertFalse(is_expected(case, wrong))


if __name__ == "__main__":
    unittest.main()
