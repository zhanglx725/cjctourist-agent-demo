"""Offline E5-A3 tests for evidence-only neutral narration rendering."""

from __future__ import annotations

from dataclasses import replace
import json
import unittest

from guidance_evidence_bundle import build_guidance_evidence_bundle
from guidance_policy import build_guidance_policy
from guide_program_planner import plan_stop_program
from narration_coverage import commit_introductions
from narration_rendering import render_guidance_evidence
from visitor_profile import create_visitor_profile


def _entry(document: str, title: str, source: str, content: str) -> dict:
    return {"document": document, "title_path": ["知识库", title], "source_ids": [source], "content": content}


class NarrationRenderingTests(unittest.TestCase):
    def setUp(self):
        self.program = plan_stop_program("stop_front_courtyard_center", 240, interests=["灰塑"], detail_level="standard")
        self.primary = self.program.selected_items[0]
        self.second = self.program.selected_items[1]

    def _bundle(self, *, coverage=None, no_craft: bool = False, wrong_primary: bool = False):
        def rag(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                evidence = [] if no_craft else [_entry("07_ornament_crafts.md", "灰塑", "S07", "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。制作时可用石灰等材料堆塑，形成有层次的造型。")]
            elif self.primary.name in query:
                title = "福禄寿" if wrong_primary else self.primary.name
                evidence = [_entry("08_ornament_items.md", title, "S08", f"{title}全身朱红色，独角，造型凌空而下。这个题材源自民间传说，寓意辟邪保平安。")]
            else:
                evidence = [_entry("08_ornament_items.md", self.second.name, "S09", f"{self.second.name}表现吉祥题材，构图具有装饰层次。其寓意寄托对美好生活的祈盼。")]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)
        return build_guidance_evidence_bundle(self.program, coverage, rag)

    def test_first_craft_precedes_object_and_is_not_repeated(self):
        result = render_guidance_evidence(self.program, self._bundle())
        self.assertIn("先认识灰塑", result.visitor_message)
        self.assertLess(result.visitor_message.index("先认识灰塑"), result.visitor_message.index(self.primary.name))
        self.assertEqual(result.visitor_message.count("先认识灰塑"), 1)

    def test_repeat_craft_is_only_a_brief_recap(self):
        coverage = commit_introductions(None, [{"subject_kind": "craft", "subject_id": "灰塑", "source_ids": ["S07"], "introduced_by": "stop_guidance", "node_id": self.program.node_id, "turn_id": "turn:1"}])
        bundle = self._bundle(coverage=coverage)
        result = render_guidance_evidence(self.program, bundle)
        self.assertNotIn("先认识灰塑", result.visitor_message)
        self.assertIn("已经介绍过", result.visitor_message)
        self.assertNotIn("灰塑", result.rendered_craft_ids)
        self.assertEqual(coverage.introduced_craft_ids, ("灰塑",))

    def test_first_ornament_contains_location_shape_and_story_backed_by_sources(self):
        result = render_guidance_evidence(self.program, self._bundle())
        self.assertIn(self.primary.name, result.visitor_message)
        self.assertIn(self.primary.craft, result.visitor_message)
        self.assertIn("独角", result.visitor_message)
        self.assertIn("传说", result.visitor_message)
        self.assertIn("S08", result.used_source_ids)
        self.assertIn(self.primary.ornament_id, result.rendered_ornament_ids)

    def test_wrong_object_evidence_cannot_enter_primary_segment_or_candidate(self):
        result = render_guidance_evidence(self.program, self._bundle(wrong_primary=True))
        # 福禄寿 may still be the separately selected second reviewed object;
        # the safety boundary is that it cannot stand in for the primary item.
        self.assertNotIn(f"{self.primary.name}是一件", result.visitor_message)
        self.assertFalse(any(candidate.subject_id == self.primary.ornament_id for candidate in result.eligible_coverage_candidates))

    def test_missing_craft_evidence_removes_craft_candidate(self):
        result = render_guidance_evidence(self.program, self._bundle(no_craft=True))
        self.assertNotIn("灰塑", result.rendered_craft_ids)
        self.assertTrue(any("没有合格的工艺总述证据" in warning for warning in result.warnings))

    def test_short_budget_preserves_core_prefix_and_omits_later_items(self):
        short = replace(
            self.program,
            budget_seconds=120,
            selected_items=(replace(self.primary, planned_seconds=120), self.second),
        )
        result = render_guidance_evidence(short, self._bundle())
        self.assertEqual(result.rendered_ornament_ids, (self.primary.ornament_id,))
        self.assertEqual(result.omitted_ornament_ids, (self.second.ornament_id,))
        self.assertLessEqual(result.allocated_content_seconds, result.content_budget_seconds)
        self.assertFalse(any(candidate.subject_id == self.second.ornament_id for candidate in result.eligible_coverage_candidates))

    def test_listen_only_has_no_task_or_question(self):
        profile = create_visitor_profile(interests=["灰塑"], detail_level="standard", interaction_mode="listen_only")
        result = render_guidance_evidence(self.program, self._bundle(), build_guidance_policy(profile))
        self.assertNotIn("无需回答", result.visitor_message)
        self.assertNotIn("？", result.visitor_message)

    def test_paths_are_hidden_sources_are_only_used_when_rendered_and_inputs_are_unchanged(self):
        bundle = self._bundle()
        before_program = self.program.to_dict()
        before_bundle = bundle.to_dict()
        result = render_guidance_evidence(self.program, bundle)
        self.assertNotIn(".md", result.visitor_message)
        self.assertEqual(self.program.to_dict(), before_program)
        self.assertEqual(bundle.to_dict(), before_bundle)
        self.assertEqual(result.used_source_ids, tuple(sorted(set(result.used_source_ids))))
        self.assertEqual(result, render_guidance_evidence(self.program, bundle))


if __name__ == "__main__":
    unittest.main()
