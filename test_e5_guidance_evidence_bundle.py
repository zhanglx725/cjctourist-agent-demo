"""Offline E5-A2 evidence-bundle tests using deterministic mock RAG payloads."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import unittest

from guidance_evidence_bundle import build_guidance_evidence_bundle
from guide_program_planner import plan_stop_program
from narration_coverage import commit_introductions
from tour_qa import load_guide_cards


def _entry(document: str, title: str, source: str, content: str) -> dict:
    return {"document": document, "title_path": ["知识库", title], "source_ids": [source], "content": content}


class GuidanceEvidenceBundleTests(unittest.TestCase):
    def setUp(self):
        self.program = plan_stop_program("stop_front_courtyard_center", 240, interests=["灰塑"], detail_level="standard")
        self.primary = self.program.selected_items[0]
        self.second = self.program.selected_items[1]

    def _rag(self, calls: list[str], *, no_craft: bool = False, wrong_ornament: bool = False):
        def search(query: str) -> str:
            calls.append(query)
            if "定义 材料 技法 建筑位置 特点" in query:
                evidence = [] if no_craft else [_entry("07_ornament_crafts.md", "灰塑", "S07", "灰塑是岭南建筑装饰工艺。")]
            elif self.primary.name in query:
                title = "福禄寿" if wrong_ornament else self.primary.name
                evidence = [_entry("08_ornament_items.md", title, "S08", f"{title} 是审核条目。")]
            else:
                evidence = [_entry("08_ornament_items.md", self.second.name, "S09", f"{self.second.name} 是审核条目。")]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)
        return search

    def test_first_craft_is_retrieved_once_even_when_multiple_selected_items_share_it(self):
        # The standard front-courtyard program has two high-relevance gray
        # plaster items.  They must share one craft-overview query.
        program = self.program
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(program, None, self._rag(calls))
        craft_calls = [query for query in calls if "定义 材料 技法 建筑位置 特点" in query]
        self.assertEqual(len({item.craft for item in program.selected_items}), 1)
        self.assertEqual(len(craft_calls), 1)
        self.assertIn("灰塑", bundle.craft_overviews)

    def test_introduced_craft_does_not_retrieve_full_overview_again(self):
        coverage = commit_introductions(None, [{"subject_kind": "craft", "subject_id": "灰塑", "source_ids": ["S07"], "introduced_by": "stop_guidance", "node_id": self.program.node_id, "turn_id": "turn:1"}])
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(self.program, coverage, self._rag(calls))
        self.assertEqual(bundle.coverage_status["craft"]["灰塑"], "repeat")
        self.assertNotIn("灰塑", bundle.craft_overviews)
        self.assertFalse(any(query.startswith("灰塑 定义 材料 技法 建筑位置 特点") for query in calls))

    def test_ornament_detail_is_hard_bounded_to_reviewed_title(self):
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(self.program, None, self._rag(calls, wrong_ornament=True))
        self.assertEqual(bundle.ornament_details[self.primary.ornament_id].evidence, ())
        self.assertFalse(any(candidate.subject_id == self.primary.ornament_id for candidate in bundle.coverage_candidates))

    def test_reviewed_raw_location_enters_only_when_mapping_matches_current_node(self):
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(self.program, None, self._rag(calls))
        location = bundle.location_evidence[self.primary.ornament_id]
        self.assertEqual(location.node_id, self.program.node_id)
        self.assertEqual(location.valid, bool(self.primary.raw_location))
        self.assertEqual(location.raw_location, self.primary.raw_location if location.valid else None)

    def test_wrong_node_location_is_rejected(self):
        # Deliberately pair a front-courtyard reviewed ornament with another
        # node.  The location packet must fail closed rather than reuse it.
        program = replace(self.program, node_id="label_moon_platform", selected_items=(self.primary,))
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(program, None, self._rag(calls))
        location = bundle.location_evidence[self.primary.ornament_id]
        self.assertEqual(location.node_id, "label_moon_platform")
        self.assertFalse(location.valid)
        self.assertIsNone(location.raw_location)

    def test_empty_07_or_08_evidence_creates_no_corresponding_candidate(self):
        calls: list[str] = []
        no_craft = build_guidance_evidence_bundle(self.program, None, self._rag(calls, no_craft=True))
        self.assertFalse(any(candidate.evidence_kind == "craft_overview" for candidate in no_craft.coverage_candidates))
        no_items = build_guidance_evidence_bundle(self.program, None, lambda _: json.dumps({"evidence": []}))
        self.assertFalse(any(candidate.evidence_kind == "ornament_detail" for candidate in no_items.coverage_candidates))

    def test_new_curated_craft_sources_are_eligible_with_sources_and_subject_match(self):
        craft = self.primary.craft

        def search(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                evidence = [
                    _entry("12_craft_process_and_transmission.md", f"{craft}：材料与完整流程", "S12", f"{craft}制作需要按工序完成。"),
                    _entry("10_people_builders_craftspeople.md", "无关人物", "S10", f"此人研究过{craft}。"),
                ]
            else:
                evidence = [_entry("08_ornament_items.md", self.primary.name, "S08", f"{self.primary.name}是审核条目。")]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        bundle = build_guidance_evidence_bundle(self.program, None, search)
        documents = {
            entry["document"]
            for packet in bundle.craft_overviews.values()
            for entry in packet.evidence
        }
        self.assertIn("12_craft_process_and_transmission.md", documents)
        self.assertNotIn("10_people_builders_craftspeople.md", documents)

    def test_literary_card_can_support_exact_reviewed_ornament_title(self):
        def search(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                evidence = [_entry("07_ornament_crafts.md", self.primary.craft, "S07", f"{self.primary.craft}是建筑装饰工艺。")]
            else:
                evidence = [
                    _entry("13_literary_citation_cards.md", f"引用卡：{self.primary.name}", "S13", f"{self.primary.name}的引用须区分直接相关与借用诗意。"),
                    _entry("13_literary_citation_cards.md", "其他装饰", "S13", f"正文顺带提到{self.primary.name}。"),
                ]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        bundle = build_guidance_evidence_bundle(self.program, None, search)
        packet = bundle.ornament_details[self.primary.ornament_id]
        self.assertEqual(len(packet.evidence), 1)
        self.assertIn(self.primary.name, packet.evidence[0]["title_path"][-1])

    def test_rag_failure_is_closed_and_inputs_are_unchanged(self):
        coverage = commit_introductions(None, [])
        before_coverage = coverage.to_dict()
        before_program = self.program.to_dict()
        bundle = build_guidance_evidence_bundle(self.program, coverage, lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(bundle.source_ids, ())
        self.assertEqual(bundle.coverage_candidates, ())
        self.assertEqual(coverage.to_dict(), before_coverage)
        self.assertEqual(self.program.to_dict(), before_program)

    def test_sources_are_stable_and_b3_compatibility_view_remains_available(self):
        calls: list[str] = []
        bundle = build_guidance_evidence_bundle(self.program, None, self._rag(calls))
        self.assertEqual(bundle.source_ids, tuple(sorted(set(bundle.source_ids))))
        self.assertEqual(set(bundle.evidence_by_item), {item.ornament_id for item in self.program.selected_items})


if __name__ == "__main__":
    unittest.main()
