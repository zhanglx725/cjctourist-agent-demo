from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    narration_continuation_control_node,
    route_after_narration_continuation_control,
    route_initial_request,
)
from narration_budget import NarrationContinuation
from narration_content_plan import NarrationFact


def _continuation(token=":front:ancient_scholar"):
    return NarrationContinuation(
        stop_id="front", style_id="ancient_scholar",
        remaining_facts=(NarrationFact(
            "craft:灰塑:000", "craft_background", "屋脊可见灰塑。",
        ),),
        published_fact_ids=("space:front:000",), freshness_token=token,
        budget_seconds=60,
    ).to_dict()


def _state(text="继续"):
    return {
        "messages": [HumanMessage(content=text)],
        "tour_state": {
            "route_status": "touring", "selected_route_id": None,
            "current_stop_id": "front",
        },
        "narration_continuation": _continuation(),
        "narration_continuation_commit": {"status": "guided_e5"},
    }


class NarrationContinuationGraphTests(unittest.TestCase):
    def test_exact_continue_routes_before_general_intent_handling(self):
        self.assertEqual(
            route_initial_request(_state()), "narration_continuation_control",
        )
        self.assertNotEqual(
            route_initial_request(_state("继续前往下一站")),
            "narration_continuation_control",
        )

    def test_fresh_continue_restores_plan_and_pending_commit(self):
        update = narration_continuation_control_node(_state())
        self.assertEqual(update["narration_content_plan"]["facts"][0]["statement"], "屋脊可见灰塑。")
        self.assertEqual(update["pending_role_narration_commit"]["status"], "guided_e5")
        self.assertEqual(
            route_after_narration_continuation_control({**_state(), **update}),
            "role_narration_generation",
        )

    def test_skip_clears_continuation_without_restoring_a_plan(self):
        update = narration_continuation_control_node(_state("跳过剩余内容"))
        self.assertIsNone(update["narration_continuation"])
        self.assertIsNone(update["narration_continuation_commit"])
        self.assertIn("已跳过", update["messages"][0].content)

    def test_route_or_stop_change_invalidates_pending_facts(self):
        state = _state()
        state["tour_state"] = {**state["tour_state"], "current_stop_id": "rear"}
        update = narration_continuation_control_node(state)
        self.assertIsNone(update["narration_continuation"])
        self.assertIsNone(update["narration_continuation_commit"])
        self.assertIn("已失效", update["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
