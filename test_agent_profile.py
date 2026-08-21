"""No-network checks for Agent timing helpers."""

import unittest
from langchain_core.messages import HumanMessage

from agent_graph import (
    DEFAULT_DEEPSEEK_MAX_TOKENS,
    DEFAULT_DEEPSEEK_MODEL,
    MAX_TOOL_LOOPS,
    _append_metric,
    should_direct_rag,
    should_direct_route,
    direct_route_node,
)


class AgentProfileTests(unittest.TestCase):
    def test_metric_is_appended_without_mutating_input(self):
        initial = [{"node": "previous", "elapsed_seconds": 0.1}]
        result = _append_metric({"performance_metrics": initial}, "rag_tool", 1.23456)
        self.assertEqual(len(initial), 1)
        self.assertEqual(result[-1], {"node": "rag_tool", "elapsed_seconds": 1.2346})

    def test_default_answer_budget_is_bounded(self):
        self.assertEqual(DEFAULT_DEEPSEEK_MAX_TOKENS, 450)
        self.assertEqual(DEFAULT_DEEPSEEK_MODEL, "deepseek-v4-flash")

    def test_tool_loop_limit_leaves_room_for_one_evidence_answer(self):
        self.assertGreaterEqual(MAX_TOOL_LOOPS, 1)

    def test_known_cultural_site_facts_skip_tool_selection_llm(self):
        self.assertTrue(should_direct_rag("陈家祠是什么？"))
        self.assertTrue(should_direct_rag("百鸟朝凤是什么装饰？"))
        self.assertFalse(should_direct_rag("你好，今天适合出门吗？"))

    def test_route_request_skips_tool_selection_llm(self):
        self.assertTrue(should_direct_route("我只有半小时，帮我规划路线"))
        self.assertTrue(should_direct_route("60分钟看工艺怎么逛？"))

    def test_direct_route_returns_complete_deterministic_message(self):
        result = direct_route_node(
            {"messages": [HumanMessage(content="我只有半小时，帮我规划路线")], "performance_metrics": []}
        )
        message = result["messages"][0].content
        self.assertNotIn("为什么选择这条路线", message)
        self.assertIn("沿途可以重点看到", message)
        self.assertIn("游览后", message)
        self.assertIn("路线主线", message)
        self.assertIn(
            "提示：时间基于官网地图与已核对路线估算，现场通行、驻足和开放情况请以馆方安排为准。",
            message,
        )
        self.assertEqual(result["selected_route_id"], "highlights_30")

    def test_non_anchor_duration_uses_dynamic_route_after_a0_review(self):
        result = direct_route_node(
            {"messages": [HumanMessage(content="我有45分钟，想看灰塑，帮我规划路线")], "performance_metrics": []}
        )
        self.assertEqual(result["selected_route_id"], "dynamic_45")
        self.assertEqual(result["active_route_plan"]["route_strategy"], "dynamic")
        self.assertEqual(
            result["active_route_plan"]["full_path_node_ids"][-1],
            "stop_front_courtyard_center",
        )


if __name__ == "__main__":
    unittest.main()
