"""P2-05 rollout behavior for the first controlled-knowledge bridge."""

from __future__ import annotations

import json
import os
from unittest.mock import patch
import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    _rollout_thread_id,
    controlled_knowledge_rollout_node,
    route_initial_request,
)
from controlled_rollout import (
    CONTROLLED_KNOWLEDGE,
    ReadOnlyRollout,
    RolloutMode,
    evaluation_record,
    rollout_from_environment,
)


QUERY = "团队订单电子发票规则"
EVIDENCE = [{
    "category": "ticketing_snapshot",
    "content": "团队订单电子发票规则：购买后 30 日内可申请；发票开具后不可修改且不能退票。",
    "source_ids": ["S06"],
}]


def _state() -> dict:
    return {"messages": [HumanMessage(content=QUERY)], "performance_metrics": []}


class ControlledRolloutTests(unittest.TestCase):
    def test_thread_id_supports_api_metadata_and_local_configurable_context(self):
        self.assertEqual(_rollout_thread_id({"configurable": {"thread_id": "local-a"}}), "local-a")
        self.assertEqual(_rollout_thread_id({"metadata": {"thread_id": "api-a"}}), "api-a")
        self.assertEqual(_rollout_thread_id({"metadata": {"langgraph_thread_id": "api-b"}}), "api-b")

    def test_configuration_is_capability_scoped_and_invalid_values_fail_closed(self):
        self.assertEqual(
            rollout_from_environment({
                "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
                "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": CONTROLLED_KNOWLEDGE,
            }),
            ReadOnlyRollout(RolloutMode.SHADOW, frozenset({CONTROLLED_KNOWLEDGE})),
        )
        self.assertEqual(
            rollout_from_environment({"CJC_READ_ONLY_ROLLOUT_MODE": "not-a-mode"}).mode,
            RolloutMode.OFF,
        )
        self.assertFalse(
            rollout_from_environment({
                "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
                "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "single_fact",
            }).enabled(CONTROLLED_KNOWLEDGE)
        )

    def test_off_keeps_the_existing_direct_rag_route(self):
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "off",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": CONTROLLED_KNOWLEDGE,
        }, clear=False):
            self.assertEqual(route_initial_request(_state()), "direct_rag")

    def test_shadow_preserves_legacy_message_and_records_per_thread_difference(self):
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": CONTROLLED_KNOWLEDGE,
        }, clear=False), patch(
            "agent_graph._search_controlled_knowledge_evidence",
            return_value=json.dumps({"evidence": EVIDENCE}, ensure_ascii=False),
        ):
            self.assertEqual(route_initial_request(_state()), "controlled_knowledge_rollout")
            update = controlled_knowledge_rollout_node(
                _state(), {"configurable": {"thread_id": "shadow-a"}},
            )
        audit = update["controlled_rollout_evaluations"][-1]
        self.assertEqual((audit["thread_id"], audit["mode"], audit["outcome"]), ("shadow-a", "shadow", "candidate_shadow"))
        self.assertEqual(audit["candidate_status"], "ok")
        self.assertTrue(audit["same_message"])
        self.assertIn("30 日内", update["messages"][0].additional_kwargs["direct_controlled_knowledge_answer"]["message"])

    def test_active_uses_candidate_and_falls_back_to_legacy_not_raw_rag_on_failure(self):
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": CONTROLLED_KNOWLEDGE,
        }, clear=False), patch(
            "agent_graph._search_controlled_knowledge_evidence",
            return_value=json.dumps({"evidence": EVIDENCE}, ensure_ascii=False),
        ):
            active = controlled_knowledge_rollout_node(
                _state(), {"configurable": {"thread_id": "active-a"}},
            )
            with patch("agent_graph.answer_reviewed_controlled_knowledge", side_effect=RuntimeError("unavailable")):
                fallback = controlled_knowledge_rollout_node(
                    _state(), {"configurable": {"thread_id": "active-b"}},
                )
        self.assertEqual(active["controlled_rollout_evaluations"][-1]["outcome"], "candidate_active")
        audit = fallback["controlled_rollout_evaluations"][-1]
        self.assertEqual((audit["outcome"], audit["candidate_status"]), ("candidate_failed_legacy_fallback", "tool_unavailable"))
        message = fallback["messages"][0].additional_kwargs["direct_controlled_knowledge_answer"]["message"]
        self.assertIn("发票", message)
        self.assertNotIn("ticketing_snapshot", message)

    def test_evaluations_are_thread_scoped_and_controls_keep_legacy_route(self):
        first = evaluation_record("thread-a", {"status": "ok", "message": "甲"}, {"status": "ok", "message": "甲"}, mode=RolloutMode.SHADOW, outcome="candidate_shadow")
        second = evaluation_record("thread-b", {"status": "ok", "message": "乙"}, {"status": "ok", "message": "乙"}, mode=RolloutMode.SHADOW, outcome="candidate_shadow")
        self.assertNotEqual(first["thread_id"], second["thread_id"])
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": CONTROLLED_KNOWLEDGE,
        }, clear=False):
            self.assertEqual(
                route_initial_request({"messages": [HumanMessage(content="帮我规划路线")]}),
                "journey_mode_selection",
            )


if __name__ == "__main__":
    unittest.main()
