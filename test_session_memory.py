"""C9 memory-boundary checks for the local MemorySaver graph."""

from __future__ import annotations

import unittest

from agent_graph import agent_graph
from qa_context import create_qa_context


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

    def test_qa_context_isolated_between_checkpointer_threads(self):
        first_thread = "e4-4b-qa-a"
        second_thread = "e4-4b-qa-b"
        self._invoke("查看当前画像", first_thread)
        self._invoke("查看当前画像", second_thread)
        context = create_qa_context(
            query_node_id="label_moon_platform",
            origin="explicit_node",
            subject_kind="craft",
            subject_terms=["石雕"],
            answer_mode="current_point_craft_features",
            follow_up_allowed=True,
            physical_node_id_snapshot="stop_rear_west_courtyard",
        )
        first_config = {"configurable": {"thread_id": first_thread}}
        second_config = {"configurable": {"thread_id": second_thread}}
        agent_graph.update_state(first_config, {"qa_context": context})
        stored = agent_graph.get_state(first_config).values["qa_context"]
        self.assertEqual(stored["query_node_id"], context["query_node_id"])
        self.assertEqual(stored["source_response_kind"], "tour_qa")
        self.assertIsNone(agent_graph.get_state(second_config).values.get("qa_context"))


if __name__ == "__main__":
    unittest.main()
