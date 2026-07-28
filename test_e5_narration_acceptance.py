"""Offline E5-C validation for narration evaluation data and evidence traces.

This suite deliberately validates static E5-C fixtures only.  It does not
invoke an LLM, network, LangSmith, LangGraph, or an E5-A coverage mock.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).parent
DATA_ROOT = ROOT / "data" / "chen_clan_academy"
CASES_PATH = DATA_ROOT / "evaluation" / "e5_narration_cases_v1.yaml"
AUDIT_PATH = DATA_ROOT / "evaluation" / "e5_evidence_coverage_audit_v1.yaml"
NODE_CARDS_PATH = DATA_ROOT / "routes" / "node_guide_cards_v1.json"
SOURCE_REGISTRY_PATH = DATA_ROOT / "sources" / "source_registry.md"

BASELINE_COMMIT = "824f8446fb2f23c5adb0ed7491e69b8a39c636cb"
BRANCH = "codex/e5-c-narration-evaluation"

REQUIRED_CASE_FIELDS = {
    "case_id",
    "runtime_readiness",
    "evaluation_phase",
    "current_node_id",
    "point_name",
    "craft",
    "ornament_id",
    "ornament_name",
    "profile_fixture",
    "stage",
    "input",
    "expected_evidence_documents",
    "expected_source_ids",
    "expected_object_whitelist",
    "expected_invariants",
    "hard_failure_conditions",
    "notes",
}
ALLOWED_READINESS = {"executable_static", "blocked_pending_e5_a"}
ALLOWED_PHASES = {
    "static_evidence_audit",
    "current_runtime_invariant",
    "future_e5_a_runtime",
    "future_e5_b_runtime",
    "langsmith_manual",
}
CORE_HARD_FAILURE_FRAGMENTS = (
    "当前点审核对象白名单",
    "虚构现有证据",
    "无来源的文化结论",
    "修改 TourState",
    "研究观点",
)


class E5NarrationAcceptanceDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases_payload = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
        cls.audit_payload = yaml.safe_load(AUDIT_PATH.read_text(encoding="utf-8"))
        cls.cards_payload = json.loads(NODE_CARDS_PATH.read_text(encoding="utf-8"))
        cls.source_registry = SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")
        cls.cards_by_node = {
            card["node_id"]: card for card in cls.cards_payload["cards"]
        }
        cls.ornaments_by_id = {
            ornament["ornament_id"]: ornament
            for card in cls.cards_payload["cards"]
            for ornament in card["ornaments"]
        }

    def test_yaml_headers_and_case_counts_are_frozen(self) -> None:
        self.assertEqual(self.cases_payload["schema_version"], "e5_narration_cases_v1")
        self.assertEqual(self.cases_payload["module"], "e5_c_narration_evaluation")
        self.assertEqual(self.cases_payload["baseline_commit"], BASELINE_COMMIT)
        self.assertEqual(self.cases_payload["branch"], BRANCH)
        self.assertEqual(self.audit_payload["schema_version"], "e5_evidence_coverage_audit_v1")
        self.assertEqual(self.audit_payload["module"], "e5_c_narration_evaluation")
        self.assertEqual(self.audit_payload["baseline_commit"], BASELINE_COMMIT)
        self.assertEqual(self.audit_payload["branch"], BRANCH)

        cases = self.cases_payload["cases"]
        self.assertEqual(len(cases), 19)
        self.assertEqual(
            sum(case["runtime_readiness"] == "executable_static" for case in cases),
            12,
        )
        self.assertEqual(
            sum(case["runtime_readiness"] == "blocked_pending_e5_a" for case in cases),
            7,
        )

    def test_case_schema_ids_and_controlled_values(self) -> None:
        cases = self.cases_payload["cases"]
        case_ids = [case["case_id"] for case in cases]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in cases:
            self.assertTrue(REQUIRED_CASE_FIELDS.issubset(case), case["case_id"])
            self.assertIn(case["runtime_readiness"], ALLOWED_READINESS, case["case_id"])
            self.assertIn(case["evaluation_phase"], ALLOWED_PHASES, case["case_id"])
            self.assertIsInstance(case["expected_evidence_documents"], list)
            self.assertIsInstance(case["expected_source_ids"], list)
            self.assertIsInstance(case["expected_object_whitelist"], list)
            self.assertIsInstance(case["expected_invariants"], list)
            self.assertIsInstance(case["hard_failure_conditions"], list)

    def test_required_points_crafts_profiles_and_stages_are_covered(self) -> None:
        cases = self.cases_payload["cases"]
        covered_nodes = {case["current_node_id"] for case in cases}
        self.assertTrue(
            {
                "stop_front_courtyard_center",
                "label_moon_platform",
                "stop_front_courtyard_north",
                "stop_rear_west_courtyard",
            }.issubset(covered_nodes)
        )
        self.assertTrue({"灰塑", "木雕", "石雕", "陶塑"}.issubset(
            {case["craft"] for case in cases}
        ))
        self.assertTrue(
            {
                "neutral",
                "child",
                "family",
                "student_research",
                "professional",
                "listen_only",
                "mixed_group",
            }.issubset({case["profile_fixture"]["fixture"] for case in cases})
        )
        self.assertTrue(
            {
                "首次工艺讲解",
                "后续重复工艺",
                "首次文物讲解",
                "再讲详细一点",
                "当前点知识问答",
                "短时间预算",
            }.issubset({case["stage"] for case in cases})
        )

    def test_case_objects_belong_to_real_current_node_whitelists(self) -> None:
        for case in self.cases_payload["cases"]:
            node_id = case["current_node_id"]
            self.assertIn(node_id, self.cards_by_node, case["case_id"])
            self.assertIn(case["ornament_id"], self.ornaments_by_id, case["case_id"])
            ornament = self.ornaments_by_id[case["ornament_id"]]
            self.assertEqual(ornament["name"], case["ornament_name"], case["case_id"])

            approved_ids = {
                item["ornament_id"] for item in self.cards_by_node[node_id]["ornaments"]
            }
            self.assertIn(case["ornament_id"], approved_ids, case["case_id"])
            self.assertEqual(set(case["expected_object_whitelist"]), approved_ids, case["case_id"])

    def test_evidence_documents_and_source_ids_are_traceable(self) -> None:
        for case in self.cases_payload["cases"]:
            self.assertTrue(case["expected_evidence_documents"], case["case_id"])
            self.assertTrue(case["expected_source_ids"], case["case_id"])
            for document in case["expected_evidence_documents"]:
                self.assertTrue((ROOT / document).is_file(), (case["case_id"], document))
            for source_id in case["expected_source_ids"]:
                self.assertIn(f"| {source_id} |", self.source_registry, case["case_id"])

    def test_first_introduction_and_location_declarations_reference_right_evidence(self) -> None:
        cases = self.cases_payload["cases"]
        first_craft = [case for case in cases if case["stage"] == "首次工艺讲解"]
        first_ornament = [case for case in cases if case["stage"] == "首次文物讲解"]
        self.assertTrue(first_craft)
        self.assertTrue(first_ornament)
        for case in first_craft:
            self.assertIn(
                "data/chen_clan_academy/knowledge/07_ornament_crafts.md",
                case["expected_evidence_documents"],
                case["case_id"],
            )
        for case in first_ornament:
            self.assertIn(
                "data/chen_clan_academy/knowledge/08_ornament_items.md",
                case["expected_evidence_documents"],
                case["case_id"],
            )
        for case in cases:
            if "raw_location" in " ".join(case["expected_invariants"]):
                self.assertTrue(
                    "data/chen_clan_academy/knowledge/09_ornament_locations.md"
                    in case["expected_evidence_documents"]
                    or "data/chen_clan_academy/routes/node_guide_cards_v1.json"
                    in case["expected_evidence_documents"],
                    case["case_id"],
                )

    def test_static_invariants_and_hard_failure_boundaries_are_declared(self) -> None:
        for case in self.cases_payload["cases"]:
            conditions = "\n".join(case["hard_failure_conditions"])
            invariants = "\n".join(case["expected_invariants"])
            for fragment in CORE_HARD_FAILURE_FRAGMENTS:
                self.assertIn(fragment, conditions, case["case_id"])
            self.assertIn("TourState", invariants, case["case_id"])
            if case["stage"] == "短时间预算":
                self.assertIn("超出 StopProgram", conditions, case["case_id"])
                self.assertIn("StopProgram", conditions + "\n" + invariants, case["case_id"])
            if case["profile_fixture"]["fixture"] == "listen_only":
                self.assertIn("listen_only 模式主动", conditions, case["case_id"])
                self.assertTrue(
                    "不得主动" in invariants or "任务式表达" in invariants,
                    case["case_id"],
                )

    def test_e5a_dependent_cases_are_recorded_as_blocked_not_passed(self) -> None:
        cases_by_id = {case["case_id"]: case for case in self.cases_payload["cases"]}
        expected_blocked = {
            "e5_nar_001",
            "e5_nar_002",
            "e5_nar_003",
            "e5_nar_004",
            "e5_nar_006",
            "e5_nar_007",
            "e5_nar_008",
        }
        self.assertTrue(expected_blocked.issubset(cases_by_id))
        for case_id in expected_blocked:
            case = cases_by_id[case_id]
            self.assertEqual(case["runtime_readiness"], "blocked_pending_e5_a", case_id)
            self.assertEqual(case["evaluation_phase"], "future_e5_a_runtime", case_id)

        for case in self.cases_payload["cases"]:
            if case["runtime_readiness"] == "blocked_pending_e5_a":
                self.assertEqual(case["evaluation_phase"], "future_e5_a_runtime", case["case_id"])

    def test_audit_subject_coverage_and_known_gap_are_preserved(self) -> None:
        records = self.audit_payload["records"]
        self.assertEqual(len(records), 12)
        by_subject = {record["subject_id"]: record for record in records}
        self.assertTrue(
            {
                "craft:灰塑",
                "craft:木雕",
                "craft:石雕",
                "craft:陶塑",
                "orn_005",
                "orn_008",
                "orn_078",
                "orn_001",
                "orn_032",
                "orn_072",
                "orn_089",
                "orn_083",
            }.issubset(by_subject)
        )

        gap_record = by_subject["orn_083"]
        self.assertEqual(gap_record["node_mapping_status"], "mapping_present_with_malformed_craft_value")
        self.assertEqual(gap_record["evidence_coverage_status"], "partial_data_normalization_gap")
        self.assertEqual(len(gap_record["findings"]), 1)
        finding = gap_record["findings"][0]
        self.assertEqual(finding["finding_id"], "e5_cov_001")
        self.assertEqual(finding["subject_id"], "orn_083")
        self.assertEqual(finding["severity"], "P2")
        self.assertEqual(finding["recommended_owner"], "spatial_data_owner")

    def test_audit_records_trace_real_data_except_declared_orn083_gap(self) -> None:
        required_audit_fields = {
            "subject_id",
            "subject_kind",
            "subject_name",
            "craft",
            "affected_nodes",
            "evidence_documents",
            "source_ids",
            "raw_location_status",
            "node_mapping_status",
            "alias_consistency_status",
            "evidence_coverage_status",
            "findings",
        }
        for record in self.audit_payload["records"]:
            self.assertTrue(required_audit_fields.issubset(record), record["subject_id"])
            self.assertTrue(record["evidence_documents"], record["subject_id"])
            self.assertTrue(record["source_ids"], record["subject_id"])
            for document in record["evidence_documents"]:
                self.assertTrue((ROOT / document).is_file(), (record["subject_id"], document))
            for source_id in record["source_ids"]:
                self.assertIn(f"| {source_id} |", self.source_registry, record["subject_id"])

            if record["subject_kind"] != "ornament":
                continue
            ornament = self.ornaments_by_id[record["subject_id"]]
            approved_nodes = {
                card["node_id"]
                for card in self.cards_payload["cards"]
                if any(item["ornament_id"] == record["subject_id"] for item in card["ornaments"])
            }
            self.assertEqual(set(record["affected_nodes"]), approved_nodes, record["subject_id"])
            if record["subject_id"] == "orn_083":
                self.assertNotEqual(ornament["craft"], record["craft"])
                continue
            self.assertEqual(ornament["name"], record["subject_name"], record["subject_id"])
            self.assertEqual(ornament["craft"], record["craft"], record["subject_id"])


if __name__ == "__main__":
    unittest.main()
