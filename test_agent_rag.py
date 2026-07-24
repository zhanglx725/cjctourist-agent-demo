"""Tests for Agent-to-retriever integration that do not call an LLM."""

import json
import unittest
from unittest.mock import patch

from agent_graph import chen_clan_academy_rag_search


class AgentRagToolTests(unittest.TestCase):
    def test_tool_returns_structured_evidence(self):
        fake_evidence = [{"chunk_id": "02:0001", "source_ids": ["S02"]}]
        with patch("agent_graph.get_retriever") as get_retriever:
            get_retriever.return_value.search.return_value = [
                type("Evidence", (), {"to_dict": lambda self: fake_evidence[0]})()
            ]
            result = json.loads(chen_clan_academy_rag_search.invoke({"query": "陈家祠是什么"}))
        self.assertEqual(result["knowledge_base"], "local_snapshot_v1")
        self.assertEqual(result["evidence"], fake_evidence)


if __name__ == "__main__":
    unittest.main()
