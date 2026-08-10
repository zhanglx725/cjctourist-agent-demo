from __future__ import annotations

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import direct_route_node, profile_collection_node, route_proposal_shadow_node
from route_selection import recommend_route as deterministic_recommend_route


def _state(minutes: int, interests: list[str], detail_level: str) -> dict:
    return {
        "messages": [HumanMessage(content="请帮我规划路线")],
        "performance_metrics": [],
        "visitor_profile": {
            "available_minutes": minutes,
            "interests": interests,
            "detail_level": detail_level,
        },
    }


class RouteProposalShadowTests(unittest.TestCase):
    def _shadow_route(self, state: dict) -> tuple[dict, dict]:
        with patch.dict(
            os.environ,
            {
                "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
                "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "route_proposal",
            },
            clear=False,
        ):
            route = direct_route_node(state)
            audit = route_proposal_shadow_node(
                {**state, **route}, {"configurable": {"thread_id": "route-shadow-thread"}}
            )
        return route, audit

    def test_anchor_shadow_matches_the_same_legacy_selection(self):
        route, audit = self._shadow_route(_state(30, ["灰塑"], "standard"))
        record = audit["route_proposal_evaluations"][0]
        self.assertEqual(record["validation_status"], "accepted")
        self.assertTrue(record["matches_legacy"])
        self.assertEqual(record["proposal"]["selected_route_id"], route["selected_route_id"])
        self.assertEqual(record["proposal"]["guide_stop_ids"], route["active_route_plan"]["guide_stop_ids"])

    def test_dynamic_shadow_matches_the_same_legacy_selection(self):
        route, audit = self._shadow_route(_state(60, ["灰塑", "木雕"], "deep"))
        record = audit["route_proposal_evaluations"][0]
        self.assertEqual(record["validation_status"], "accepted")
        self.assertTrue(record["matches_legacy"])
        self.assertEqual(record["proposal"]["route_strategy"], route["active_route_plan"]["route_strategy"])
        self.assertEqual(record["proposal"]["estimated_total_seconds"], route["active_route_plan"]["estimated_total_seconds"])

    def test_ninety_minute_deep_selection_is_wrapped_without_new_planning(self):
        route, audit = self._shadow_route(_state(90, ["灰塑", "木雕"], "deep"))
        record = audit["route_proposal_evaluations"][0]
        self.assertEqual(record["validation_status"], "accepted")
        self.assertEqual(record["proposal"]["selected_route_id"], route["selected_route_id"])
        self.assertEqual(record["proposal"]["budget_breakdown"]["budget_seconds"], 90 * 60)

    def test_shadow_never_calls_route_selection_twice(self):
        with patch.object(agent_graph, "recommend_route", wraps=deterministic_recommend_route) as selector:
            self._shadow_route(_state(30, ["灰塑"], "standard"))
        self.assertEqual(selector.call_count, 1)

    def test_shadow_wrapper_failure_keeps_legacy_route_start(self):
        with patch.object(agent_graph, "wrap_route_selection_for_shadow", side_effect=RuntimeError):
            route, audit = self._shadow_route(_state(30, ["灰塑"], "standard"))
        self.assertIn("tour_state", route)
        record = audit["route_proposal_evaluations"][0]
        self.assertEqual(record["rejected_reason"], "shadow_wrapper_failed")

    def test_off_produces_no_shadow_candidate_or_evaluation(self):
        state = _state(30, ["灰塑"], "standard")
        with patch.dict(
            os.environ,
            {"CJC_READ_ONLY_ROLLOUT_MODE": "off", "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "route_proposal"},
            clear=False,
        ):
            route = direct_route_node(state)
            audit = route_proposal_shadow_node({**state, **route}, {})
        self.assertNotIn("route_proposal_shadow_candidate", route)
        self.assertEqual(audit, {})

    def test_invalid_profile_is_recorded_as_a_rejected_shadow_proposal(self):
        state = {"messages": [HumanMessage(content="我只有10分钟，帮我规划一条路线。")], "performance_metrics": []}
        collected = profile_collection_node(state)
        with patch.dict(
            os.environ,
            {
                "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
                "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "route_proposal",
            },
            clear=False,
        ):
            audit = route_proposal_shadow_node({**state, **collected}, {})
        record = audit["route_proposal_evaluations"][0]
        self.assertEqual(record["validation_status"], "rejected")
        self.assertEqual(record["rejected_reason"], "invalid_profile_value")
        self.assertIsNone(record["proposal"])

    def test_shadow_preserves_all_legacy_formal_route_state(self):
        state = _state(30, ["灰塑"], "standard")
        with patch.dict(
            os.environ,
            {
                "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
                "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "route_proposal",
            },
            clear=False,
        ):
            shadow = direct_route_node(state)
            formal_before = deepcopy({
                field: shadow[field]
                for field in ("selected_route_id", "active_route_plan", "tour_state", "tour_interaction_state", "visitor_profile")
            })
            audit = route_proposal_shadow_node({**state, **shadow}, {})
        for field in ("selected_route_id", "active_route_plan", "tour_state", "tour_interaction_state", "visitor_profile"):
            self.assertEqual(({**state, **shadow})[field], formal_before[field])
        self.assertIn("route_proposal_evaluations", audit)

    def test_thread_local_audits_do_not_share_history(self):
        first_route, first_audit = self._shadow_route(_state(30, ["灰塑"], "standard"))
        second_route, second_audit = self._shadow_route(_state(60, ["木雕"], "standard"))
        self.assertEqual(len(first_audit["route_proposal_evaluations"]), 1)
        self.assertEqual(len(second_audit["route_proposal_evaluations"]), 1)
        self.assertNotEqual(first_route["selected_route_id"], "")
        self.assertNotEqual(second_route["selected_route_id"], "")


if __name__ == "__main__":
    unittest.main()
