"""Offline E5-A4 integration tests for post-delivery coverage commits."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph
from agent_graph import direct_route_node, stop_guidance_node, tour_event_node
from guide_program_evidence import reexpress_current_stop_guidance
from narration_coverage import empty_narration_coverage


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class StopGuidanceCoverageIntegrationTests(unittest.TestCase):
    def _arrived(self) -> dict:
        started = direct_route_node(_state("我有30分钟，喜欢灰塑，帮我规划路线"))
        arrived = tour_event_node(_state("我到前院中部了", started))
        return {**started, **arrived}

    @staticmethod
    def _payload(query: str) -> str:
        if "定义 材料 技法 建筑位置 特点" in query:
            evidence = [{"document": "07_ornament_crafts.md", "title_path": ["工艺", "灰塑"], "source_ids": ["S07"], "content": "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。制作时可用石灰等材料堆塑，形成有层次的造型。"}]
        elif "独角狮" in query:
            evidence = [{"document": "08_ornament_items.md", "title_path": ["条目", "独角狮"], "source_ids": ["S08"], "content": "独角狮全身朱红色，独角，造型凌空而下。这个题材源自民间传说，寓意辟邪保平安。"}]
        else:
            evidence = [{"document": "08_ornament_items.md", "title_path": ["条目", "福禄寿"], "source_ids": ["S09"], "content": "福禄寿表现吉祥题材，构图具有装饰层次。其寓意寄托对美好生活的祈盼。"}]
        return json.dumps({"evidence": evidence}, ensure_ascii=False)

    def test_first_delivery_commits_only_rendered_subjects_without_tour_progress_change(self):
        state = self._arrived()
        before_tour, before_profile = deepcopy(state["tour_state"]), deepcopy(state["visitor_profile"])
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.side_effect = lambda args: self._payload(args["query"])
            update = stop_guidance_node(state)
        coverage = update["narration_coverage"]
        self.assertIn("灰塑", coverage["introduced_craft_ids"])
        self.assertIn("orn_005", coverage["introduced_ornament_ids"])
        self.assertEqual(update["active_narration_render_audit"]["coverage_commit"]["status"], "committed")
        self.assertNotIn("tour_state", update)
        self.assertEqual(state["tour_state"], before_tour)
        self.assertEqual(state["visitor_profile"], before_profile)

    def test_no_evidence_or_renderer_failure_never_commits_coverage(self):
        state = self._arrived()
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = json.dumps({"evidence": []})
            no_evidence = stop_guidance_node(state)
        self.assertEqual(no_evidence["narration_coverage"], empty_narration_coverage().to_dict())
        with patch("guide_program_evidence.render_guidance_evidence", side_effect=RuntimeError("render failed")):
            with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                rag.invoke.return_value = self._payload("独角狮")
                fallback = stop_guidance_node(state)
        self.assertEqual(fallback["narration_coverage"], empty_narration_coverage().to_dict())

    def test_craft_only_evidence_keeps_b3_object_guidance_and_does_not_commit(self):
        state = self._arrived()
        craft_only = json.dumps({"evidence": [{
            "document": "07_ornament_crafts.md", "title_path": ["工艺", "灰塑"],
            "source_ids": ["S07"],
            "content": "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。",
        }]}, ensure_ascii=False)
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = craft_only
            update = stop_guidance_node(state)
        self.assertEqual(update["narration_coverage"], empty_narration_coverage().to_dict())
        self.assertNotIn("active_narration_render_audit", update)

    def test_b3_fallback_hides_internal_source_ids_but_retains_structured_evidence(self):
        state = self._arrived()
        payloads = {
            "S07": json.dumps({"evidence": [{
                "document": "07_ornament_crafts.md", "title_path": ["工艺", "灰塑"],
                "source_ids": ["S07"],
                "content": "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。",
            }]}, ensure_ascii=False),
            "S11": json.dumps({"evidence": [{
                "document": "08_ornament_items.md", "title_path": ["条目", "独角狮"],
                "source_ids": ["S11"],
                "content": "独角狮造型凌空而下，题材寓意辟邪保平安。",
            }]}, ensure_ascii=False),
        }
        for source_id, payload in payloads.items():
            with self.subTest(source_id=source_id):
                before_tour = deepcopy(state["tour_state"])
                before_profile = deepcopy(state["visitor_profile"])
                with patch("guide_program_evidence.render_guidance_evidence", side_effect=RuntimeError("render failed")):
                    with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                        rag.invoke.return_value = payload
                        update = stop_guidance_node(state)
                visitor_message = update["messages"][-1].content
                self.assertEqual(update["narration_coverage"], empty_narration_coverage().to_dict())
                self.assertEqual(state["tour_state"], before_tour)
                self.assertEqual(state["visitor_profile"], before_profile)
                self.assertIn(source_id, {item for entry in update["retrieved_evidence"] for item in entry["source_ids"]})
                self.assertNotIn("来源：S", visitor_message)
                self.assertNotIn("source_ids", visitor_message)
                self.assertNotIn(".md", visitor_message)
                self.assertNotIn("http", visitor_message)

    def test_reexpressed_b3_guidance_hides_source_ids_but_retains_structured_evidence(self):
        state = self._arrived()
        with patch("guide_program_evidence.render_guidance_evidence", side_effect=RuntimeError("render failed")):
            with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                rag.invoke.side_effect = lambda args: self._payload(args["query"])
                initial = stop_guidance_node(state)
        rewritten = reexpress_current_stop_guidance(
            state["tour_state"], state["tour_interaction_state"], initial["active_stop_program"],
            initial["active_guidance_evidence_by_item"], state["visitor_profile"],
        )
        self.assertTrue(rewritten["ok"])
        self.assertTrue(initial["retrieved_evidence"])
        self.assertTrue(rewritten["source_ids"])
        self.assertNotIn("来源：S", rewritten["message"])
        self.assertNotIn("source_ids", rewritten["message"])

    def test_repeat_delivery_is_idempotent_and_new_route_clears_coverage(self):
        state = self._arrived()
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.side_effect = lambda args: self._payload(args["query"])
            first = stop_guidance_node(state)
            repeated = stop_guidance_node({**state, **first})
        self.assertEqual(first["narration_coverage"], repeated["narration_coverage"])
        reset = direct_route_node(_state("我有30分钟，帮我规划路线", {**state, **first}))
        self.assertEqual(reset["narration_coverage"], empty_narration_coverage().to_dict())

    def test_omitted_or_invalid_candidates_are_not_committed(self):
        state = self._arrived()
        fake = {
            "message": "有效讲解",
            "status": "guided_e5",
            "evidence": [], "stop_program": state.get("active_stop_program"), "evidence_by_item": {},
            "presentation": {"message": "有效讲解"},
            "narration_render_audit": {"node_id": state["tour_state"]["current_stop_id"], "rendered_craft_ids": [], "rendered_ornament_ids": ["orn_005"], "used_source_ids": ["S08"], "content_budget_seconds": 240, "allocated_content_seconds": 120, "omitted_ornament_ids": ["orn_008"], "warnings": []},
            "coverage_candidates": [
                {"subject_kind": "ornament", "subject_id": "orn_008", "source_ids": ["S09"], "node_id": state["tour_state"]["current_stop_id"], "evidence_kind": "ornament_detail"}
            ],
        }
        with patch("agent_graph.build_stop_guidance", return_value=fake):
            update = stop_guidance_node(state)
        self.assertEqual(update["narration_coverage"], empty_narration_coverage().to_dict())

    def test_one_invalid_record_rejects_the_entire_commit_group(self):
        state = self._arrived()
        node_id = state["tour_state"]["current_stop_id"]
        fake = {
            "message": "有效讲解",
            "status": "guided_e5",
            "evidence": [], "stop_program": state.get("active_stop_program"), "evidence_by_item": {},
            "presentation": {"message": "有效讲解"},
            "narration_render_audit": {
                "node_id": node_id, "rendered_craft_ids": [""],
                "rendered_ornament_ids": ["orn_005"], "used_source_ids": ["S07", "S08"],
                "content_budget_seconds": 240, "allocated_content_seconds": 120,
                "omitted_ornament_ids": [], "warnings": [],
            },
            "coverage_candidates": [
                {"subject_kind": "ornament", "subject_id": "orn_005", "source_ids": ["S08"], "node_id": node_id, "evidence_kind": "ornament_detail"},
                {"subject_kind": "craft", "subject_id": "", "source_ids": ["S07"], "node_id": node_id, "evidence_kind": "craft_overview"},
            ],
        }
        with patch("agent_graph.build_stop_guidance", return_value=fake):
            update = stop_guidance_node(state)
        self.assertEqual(update["narration_coverage"], empty_narration_coverage().to_dict())
        self.assertEqual(update["active_narration_render_audit"]["coverage_commit"]["status"], "atomic_commit_rejected")


if __name__ == "__main__":
    unittest.main()
