"""C9 memory-boundary checks for the local MemorySaver graph."""

from __future__ import annotations

import unittest

from agent_graph import agent_graph


class SessionMemoryTests(unittest.TestCase):
    def _invoke(self, text: str, thread_id: str):
        return agent_graph.invoke(
            {"messages": [("user", text)], "tool_loops": 0, "retrieved_evidence": [], "performance_metrics": []},
            config={"configurable": {"thread_id": thread_id}},
        )

    def test_same_thread_retains_profile_but_new_thread_isolated(self):
        first = self._invoke("给小朋友讲", "c9-memory-a")
        self.assertEqual(first["visitor_profile"]["audience_mode"], "child_friendly")
        second = self._invoke("查看当前画像", "c9-memory-a")
        self.assertEqual(second["visitor_profile"]["audience_mode"], "child_friendly")

        other = self._invoke("查看当前画像", "c9-memory-b")
        self.assertNotIn("tour_state", other)
        self.assertEqual(other.get("visitor_profile", {}).get("audience_mode", "standard"), "standard")
        self.assertNotIn("active_stop_program", other)
        self.assertEqual(other.get("retrieved_evidence", []), [])


if __name__ == "__main__":
    unittest.main()
