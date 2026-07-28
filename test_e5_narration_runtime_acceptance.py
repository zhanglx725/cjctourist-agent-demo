"""E5-D runtime-overlay integrity and production-interface acceptance checks.

The E5-C source cases remain historically frozen.  This suite validates the
separate E5-D runtime overlay and exercises the current public evidence and
rendering interfaces without treating local execution as already completed.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml

from guidance_evidence_bundle import build_guidance_evidence_bundle
from guide_program_planner import plan_stop_program
from narration_coverage import empty_narration_coverage
from narration_rendering import render_guidance_evidence


ROOT = Path(__file__).parent
CASES_PATH = ROOT / "data" / "chen_clan_academy" / "evaluation" / "e5_narration_cases_v1.yaml"
RESULTS_PATH = ROOT / "data" / "chen_clan_academy" / "evaluation" / "e5_narration_runtime_results_v1.yaml"
RUNTIME_CASE_IDS = {
    "e5_nar_001", "e5_nar_002", "e5_nar_003", "e5_nar_004",
    "e5_nar_006", "e5_nar_007", "e5_nar_008",
}
PENDING_AUTOMATED = {"pending_local_execution"}
PENDING_LANGSMITH = {"pending_langsmith"}


def _evidence(document: str, title: str, source_id: str, content: str) -> dict:
    return {"document": document, "title_path": ["knowledge", title], "source_ids": [source_id], "content": content}


class E5NarrationRuntimeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
        cls.overlay = yaml.safe_load(RESULTS_PATH.read_text(encoding="utf-8"))
        cls.source_by_id = {case["case_id"]: case for case in cls.source["cases"]}

    def test_overlay_maps_each_historical_blocked_case_once_without_rewriting_source(self):
        source_ids = {
            case["case_id"] for case in self.source["cases"]
            if case["runtime_readiness"] == "blocked_pending_e5_a"
        }
        result_ids = [record["case_id"] for record in self.overlay["results"]]
        self.assertEqual(source_ids, RUNTIME_CASE_IDS)
        self.assertEqual(set(result_ids), RUNTIME_CASE_IDS)
        self.assertEqual(len(result_ids), len(set(result_ids)))
        for record in self.overlay["results"]:
            original = self.source_by_id[record["case_id"]]
            self.assertEqual(record["baseline_readiness"], original["runtime_readiness"])
            self.assertIn(record["case_id"], record["evidence_refs"][0])

    def test_pending_overlay_never_claims_execution_or_verification(self):
        environment = self.overlay["environment"]
        self.assertEqual(environment["execution_status"], "pending_local_execution")
        self.assertEqual(environment["executed_at"], None)
        for record in self.overlay["results"]:
            self.assertIn(record["automated_test_status"], PENDING_AUTOMATED)
            self.assertIn(record["langsmith_status"], PENDING_LANGSMITH)
            self.assertEqual(record["actual_node_path"], [])
            self.assertEqual(record["actual_source_ids"], [])
            self.assertEqual(record["rendered_craft_ids"], [])
            self.assertEqual(record["rendered_ornament_ids"], [])
            self.assertIsNone(record["coverage_before"])
            self.assertIsNone(record["coverage_after"])
            self.assertIsNone(record["tour_state_before"])
            self.assertIsNone(record["tour_state_after"])
            self.assertEqual(record["finding_ids"], [])

    def test_version_references_and_required_runtime_fields_are_complete(self):
        self.assertEqual(self.overlay["schema_version"], "e5_narration_runtime_results_v1")
        self.assertEqual(self.overlay["evaluation_baseline"], "a643a5a577394b2876cbfbd3ed6d4a97f958982b")
        self.assertEqual(self.overlay["implementation_commit"], "5183b7e66745f201d5f68efd9b812a306b873b25")
        self.assertEqual(self.overlay["integration_commit"], "effc5a5")
        required = {
            "case_id", "baseline_readiness", "implementation_status", "automated_test_status",
            "langsmith_status", "actual_node_path", "actual_source_ids", "rendered_craft_ids",
            "rendered_ornament_ids", "coverage_before", "coverage_after", "tour_state_before",
            "tour_state_after", "score_by_dimension", "finding_ids", "evidence_refs", "notes",
        }
        self.assertTrue(all(required.issubset(record) for record in self.overlay["results"]))

    def test_current_public_evidence_and_rendering_interfaces_remain_auditable_and_state_free(self):
        program = plan_stop_program("stop_front_courtyard_center", 240, interests=["灰塑"], detail_level="standard")
        primary = program.selected_items[0]

        def rag(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                entries = [_evidence("07_ornament_crafts.md", "灰塑", "S10", "灰塑是岭南传统建筑装饰工艺，常见于山墙和屋脊。制作时可用石灰等材料堆塑，形成有层次的造型。")]
            elif primary.name in query:
                entries = [_evidence("08_ornament_items.md", primary.name, "S11", f"{primary.name}全身朱红色，独角，造型凌空而下。这个题材源自民间传说，寓意辟邪保平安。")]
            else:
                entries = []
            return json.dumps({"evidence": entries}, ensure_ascii=False)

        coverage = empty_narration_coverage()
        bundle = build_guidance_evidence_bundle(program, coverage, rag)
        result = render_guidance_evidence(program, bundle)
        self.assertEqual(bundle.node_id, program.node_id)
        self.assertIn(primary.ornament_id, result.rendered_ornament_ids)
        self.assertIn("S10", result.used_source_ids)
        self.assertIn("S11", result.used_source_ids)
        self.assertLessEqual(result.allocated_content_seconds, result.content_budget_seconds)
        self.assertEqual(coverage, empty_narration_coverage())


if __name__ == "__main__":
    unittest.main()
