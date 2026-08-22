"""Tests for Agent-to-retriever integration that do not call an LLM."""

import json
import unittest
from unittest.mock import patch

from agent_graph import chen_clan_academy_rag_search, should_direct_rag


class AgentRagToolTests(unittest.TestCase):
    def test_new_curated_library_topics_directly_trigger_rag(self):
        cases = (
            "有哪些参与修缮的工匠？",
            "灰塑出现开裂后怎样保护？",
            "陶塑的制作工序是什么？",
            "有没有适合这里的诗句？",
            "陈氏子弟怎样来广州应考？",
            "以前有哪些老师傅参与维护？",
            "这种装饰到底怎么做出来？",
            "这句话的出处是什么？",
            "有没有学子在这里暂住赶考？",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(should_direct_rag(text))

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
