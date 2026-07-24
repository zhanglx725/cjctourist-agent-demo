"""Regression checks for representative RAG latency benchmark coverage."""

import unittest

from rag_benchmark import CASES


class RagBenchmarkTests(unittest.TestCase):
    def test_benchmark_covers_fast_plain_and_reranked_paths(self):
        names = {case.name for case in CASES}
        self.assertIn("exact_title_fast_path", names)
        self.assertIn("plain_fact_rrf", names)
        self.assertIn("ambiguous_identity_rerank", names)


if __name__ == "__main__":
    unittest.main()
