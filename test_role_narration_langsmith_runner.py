from __future__ import annotations

import unittest
from unittest.mock import patch

from role_narration_langsmith_runner import run_role_narration_example
from tools.build_role_narration_langsmith_dataset import build_examples
from tools.build_role_narration_langsmith_fault_dataset import build_examples as build_fault_examples


class RoleNarrationLangSmithRunnerTests(unittest.TestCase):
    def test_timeout_fixture_uses_production_fallback_nodes(self):
        inputs = {
            "style_id": "dominant_ceo", "scene_kind": "stop_guidance",
            "fact_id": "craft:灰塑", "approved_fact": "该构件采用灰塑工艺。",
            "interaction_allowed": True, "failure_type": "model_failure",
        }
        result = run_role_narration_example(inputs, {
            "expected_coverage_commit_count": 1,
            "expected_fallback_on_validation_failure": True,
        })
        self.assertEqual(result["evaluation_entry"], "production_role_narration_graph_segment")
        self.assertFalse(result["full_stop_guidance_session"])
        self.assertFalse(result["commit_audit"]["active_takeover"])
        self.assertTrue(result["commit_audit"]["fallback_used"])
        self.assertEqual(result["commit_audit"]["commit_decision"], "legacy_fallback_published")
        self.assertEqual(len(result["coverage"]["introduction_records"]), 1)
        self.assertTrue(all(result["assertions"].values()))

    def test_accepted_fixture_reaches_commit_with_model_response(self):
        inputs = next(item["inputs"] for item in build_examples() if item["inputs"]["style_id"] == "ancient_scholar" and item["inputs"]["point_type"] == "craft")
        response = '{"schema_version":"role_narration_candidate_v1","style_id":"ancient_scholar","public_text":"[[FACT_000]]","used_fact_ids":["craft:灰塑"],"omitted_fact_ids":[],"self_check":{"added_new_facts":false,"role_consistent":true,"within_budget":true}}'
        with patch("agent_graph._invoke_role_narration_model", return_value=response):
            result = run_role_narration_example(inputs, {
                "expected_coverage_commit_count": 1,
                "expected_fallback_on_validation_failure": True,
            })
        self.assertEqual(result["validation"]["validation_status"], "accepted")
        self.assertTrue(result["commit_audit"]["active_takeover"])
        self.assertEqual(result["commit_audit"]["commit_decision"], "role_candidate_published")
        self.assertIn(inputs["approved_fact"], result["final_visitor_message"])
        self.assertIn("讲解结束后，您可确认是否完成本点参观。", result["final_visitor_message"])
        self.assertIn("完成本点后，下一站：月台", result["final_visitor_message"])
        self.assertNotIn("【下一步】", result["final_visitor_message"])
        self.assertTrue(all(result["assertions"].values()))

    def test_style_judge_is_optional_and_never_runs_for_a_fallback(self):
        inputs = {
            "style_id": "dominant_ceo", "scene_kind": "stop_guidance",
            "fact_id": "craft:灰塑", "approved_fact": "该构件采用灰塑工艺。",
            "interaction_allowed": True, "failure_type": "model_failure",
        }
        result = run_role_narration_example(inputs, evaluate_style_quality=True)
        self.assertEqual(result["style_quality"], {"status": "not_requested"})

    def test_fault_dataset_routes_every_case_to_real_fallback_with_assertions(self):
        for item in build_fault_examples():
            with self.subTest(case_id=item["inputs"]["case_id"]):
                result = run_role_narration_example(item["inputs"], item["outputs"])
                self.assertTrue(result["commit_audit"]["fallback_used"])
                self.assertEqual(result["commit_audit"]["commit_decision"], "legacy_fallback_published")
                self.assertTrue(all(result["assertions"].values()), result["assertions"])

    def test_fault_runner_isolated_from_natural_full_shell_flags(self):
        inputs = {
            "style_id": "cute_junior", "scene_kind": "stop_guidance",
            "fact_id": "craft:灰塑", "approved_fact": "该构件采用灰塑工艺。",
            "interaction_allowed": True, "failure_type": "model_failure",
        }
        with patch.dict("os.environ", {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "true",
        }, clear=False):
            result = run_role_narration_example(inputs, {
                "expected_coverage_commit_count": 1,
                "expected_fallback_on_validation_failure": True,
            })
        self.assertTrue(result["commit_audit"]["fallback_used"])
        self.assertEqual(result["commit_audit"]["commit_decision"], "legacy_fallback_published")


if __name__ == "__main__":
    unittest.main()
