from __future__ import annotations

import unittest

from agent_graph import deterministic_narration_fallback_node, narration_commit_node
from narration_budget import NarrationContinuation
from narration_content_plan import NarrationFact
from test_role_narration_graph import RoleNarrationGraphTests


class NarrationContinuationCommitTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RoleNarrationGraphTests()

    def test_split_commit_submits_only_subject_published_this_turn(self):
        state = self.fixture.state()
        pending = state["pending_role_narration_commit"]
        pending["coverage_candidates"].append({
            "subject_kind": "ornament", "subject_id": "麒麟",
            "source_ids": ["S2"], "evidence_kind": "ornament_detail",
            "node_id": self.fixture.STOP_ID,
        })
        pending["narration_render_audit"]["rendered_ornament_ids"] = ["麒麟"]
        pending["narration_render_audit"]["used_source_ids"].append("S2")
        state["narration_budget_decision"] = {
            "mode": "split", "selected_fact_ids": ["craft:灰塑:000"],
            "deferred_fact_ids": ["ornament:麒麟:000"],
        }
        continuation = NarrationContinuation(
            stop_id=self.fixture.STOP_ID, style_id="ancient_scholar",
            remaining_facts=(NarrationFact(
                "ornament:麒麟:000", "object_detail", "屋脊装饰中可见麒麟。",
            ),),
            published_fact_ids=("craft:灰塑:000",),
            freshness_token=f":{self.fixture.STOP_ID}:ancient_scholar", budget_seconds=60,
        ).to_dict()
        state["pending_narration_continuation"] = continuation
        state["narration_continuation_commit"] = dict(pending)
        state["narration_validation"]["validated_public_message"] = (
            state["role_narration_candidate"]["public_text"]
        )
        with self.fixture.active_environment():
            result = narration_commit_node(state)
        self.assertEqual(result["narration_coverage"]["introduced_craft_ids"], ["灰塑"])
        self.assertEqual(result["narration_coverage"]["introduced_ornament_ids"], [])
        self.assertEqual(result["narration_continuation"], continuation)
        self.assertIsNone(result["pending_narration_continuation"])
        self.assertNotIn("讲解结束后", result["messages"][0].content)

    def test_fallback_does_not_consume_existing_continuation(self):
        state = self.fixture.state()
        continuation = NarrationContinuation(
            stop_id=self.fixture.STOP_ID, style_id="ancient_scholar",
            remaining_facts=(NarrationFact(
                "ornament:麒麟:000", "object_detail", "屋脊装饰中可见麒麟。",
            ),),
            published_fact_ids=("craft:灰塑:000",),
            freshness_token=f":{self.fixture.STOP_ID}:ancient_scholar", budget_seconds=60,
        ).to_dict()
        evidence = {"status": "guided_e5"}
        state["narration_continuation"] = continuation
        state["narration_continuation_commit"] = evidence
        state["pending_narration_continuation"] = {**continuation, "status": "completed"}
        result = deterministic_narration_fallback_node(state)
        self.assertNotIn("narration_continuation", result)
        self.assertEqual(result["narration_continuation_commit"], evidence)
        self.assertIsNone(result["pending_narration_continuation"])


if __name__ == "__main__":
    unittest.main()
