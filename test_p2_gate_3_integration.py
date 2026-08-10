"""Final P2 integration boundaries: audit-only shadows must stay non-authoritative."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    atomic_read_plan_shadow_node,
    replan_proposal_shadow_node,
    route_proposal_shadow_node,
)
from controlled_rollout import (
    ATOMIC_READ_PLAN,
    CONTROLLED_KNOWLEDGE,
    REPLAN_PROPOSAL,
    ROUTE_PROPOSAL,
    STATE_TRANSITION,
    rollout_from_environment,
)
from route_planner import plan_template
from tour_interaction import initialize_interaction
from tour_state import start_tour


class P2Gate3IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.all_shadow = {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": (
                "controlled_knowledge,atomic_read_plan,route_proposal,"
                "replan_proposal,state_transition"
            ),
        }

    def test_all_p2_capabilities_observe_only_in_the_final_shadow_configuration(self) -> None:
        with patch.dict(os.environ, self.all_shadow, clear=False):
            rollout = rollout_from_environment()
        for capability in (
            CONTROLLED_KNOWLEDGE,
            ATOMIC_READ_PLAN,
            ROUTE_PROPOSAL,
            REPLAN_PROPOSAL,
            STATE_TRANSITION,
        ):
            self.assertTrue(rollout.observes(capability))
            self.assertFalse(rollout.enabled(capability))

    def test_read_only_shadow_updates_are_audit_fields_not_formal_route_or_replan_writes(self) -> None:
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        replan = {
            "status": "awaiting_route_confirmation",
            "origin_node_id": "stop_front_courtyard_center",
            "physical_node_snapshot": "stop_front_courtyard_center",
            "route_id": "highlights_30",
            "remaining_minutes": 30,
            "guide_stop_ids": ["stop_front_courtyard_center"],
            "visited_stop_ids_snapshot": [],
            "skipped_stop_ids_snapshot": [],
        }
        state = {
            "messages": [HumanMessage(content="陈家祠什么时候开始筹建，再团队订单电子发票规则是什么？")],
            "tour_state": tour,
            "tour_interaction_state": interaction,
            "pending_replan_proposal": replan,
            "atomic_read_plan_evaluations": [],
            "replan_proposal_evaluations": [],
        }
        protected = {
            name: state.get(name)
            for name in ("tour_state", "tour_interaction_state", "pending_replan_proposal")
        }
        with patch.dict(os.environ, self.all_shadow, clear=False):
            atomic = atomic_read_plan_shadow_node(state, {"configurable": {"thread_id": "gate3-a"}})
            replan_audit = replan_proposal_shadow_node(state, {"configurable": {"thread_id": "gate3-a"}})
        self.assertEqual(protected["tour_state"], state["tour_state"])
        self.assertEqual(protected["tour_interaction_state"], state["tour_interaction_state"])
        self.assertEqual(protected["pending_replan_proposal"], state["pending_replan_proposal"])
        self.assertEqual(set(atomic), {"atomic_read_plan_evaluations"})
        self.assertEqual(set(replan_audit), {"replan_proposal_evaluations"})

    def test_route_shadow_uses_its_existing_legacy_selection_without_second_planning(self) -> None:
        # The dedicated P2-02 suite verifies selector call count.  Gate 3
        # asserts the integrated audit remains an append-only field.
        legacy = {
            "route_strategy": "anchor_template",
            "guide_stop_ids": ["stop_front_courtyard_center"],
            "estimated_total_seconds": 600,
        }
        state = {
            "messages": [HumanMessage(content="帮我规划路线")],
            "visitor_profile": {
                "available_minutes": 30,
                "interests": ["灰塑"],
                "detail_level": "standard",
            },
            "selected_route_id": "highlights_30",
            "active_route_plan": legacy,
            "route_proposal_shadow_candidate": {
                "validation_status": "accepted",
                "rejected_reason": None,
                "proposal": {
                    "selected_route_id": "highlights_30",
                    "guide_stop_ids": legacy["guide_stop_ids"],
                    "estimated_total_seconds": legacy["estimated_total_seconds"],
                    "route_strategy": legacy["route_strategy"],
                },
            },
            "route_proposal_evaluations": [],
        }
        with patch.dict(os.environ, self.all_shadow, clear=False):
            update = route_proposal_shadow_node(state, {"configurable": {"thread_id": "gate3-b"}})
        self.assertEqual(set(update), {"route_proposal_evaluations"})
        self.assertTrue(update["route_proposal_evaluations"][0]["matches_legacy"])


if __name__ == "__main__":
    unittest.main()
