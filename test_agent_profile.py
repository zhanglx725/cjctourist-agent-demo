"""No-network checks for Agent timing helpers."""

import unittest

from agent_graph import (
    DEFAULT_DEEPSEEK_MAX_TOKENS,
    MAX_TOOL_LOOPS,
    _append_metric,
    should_direct_rag,
)


class AgentProfileTests(unittest.TestCase):
    def test_metric_is_appended_without_mutating_input(self):
        initial = [{"node": "previous", "elapsed_seconds": 0.1}]
        result = _append_metric({"performance_metrics": initial}, "rag_tool", 1.23456)
        self.assertEqual(len(initial), 1)
        self.assertEqual(result[-1], {"node": "rag_tool", "elapsed_seconds": 1.2346})

    def test_default_answer_budget_is_bounded(self):
        self.assertEqual(DEFAULT_DEEPSEEK_MAX_TOKENS, 450)

    def test_tool_loop_limit_leaves_room_for_one_evidence_answer(self):
        self.assertGreaterEqual(MAX_TOOL_LOOPS, 1)

    def test_known_cultural_site_facts_skip_tool_selection_llm(self):
        self.assertTrue(should_direct_rag("陈家祠是什么？"))
        self.assertTrue(should_direct_rag("百鸟朝凤是什么装饰？"))
        self.assertFalse(should_direct_rag("你好，今天适合出门吗？"))


if __name__ == "__main__":
    unittest.main()
