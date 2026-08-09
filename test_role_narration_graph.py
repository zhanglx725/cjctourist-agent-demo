from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent_graph import (
    _invoke_role_narration_model,
    deterministic_narration_fallback_node,
    role_narration_generation_node,
    narration_validation_node,
    narration_commit_node,
    route_after_narration_validation,
)
from narration_coverage import empty_narration_coverage
from narration_content_plan import NarrationContentPlan, NarrationFact


class RoleNarrationGraphTests(unittest.TestCase):
    def state(self):
        legacy = "【工艺背景：灰塑】\n\n屋脊可见灰塑。\n\n【下一步】\n\n讲解结束后可继续。"
        return {
            "messages": [AIMessage(id="legacy-message", content=legacy, additional_kwargs={"stop_guidance": True})],
            "tour_state": {"route_status": "touring", "current_stop_id": "front"},
            "narration_coverage": empty_narration_coverage().to_dict(),
            "pending_role_narration_commit": {
                "status": "guided_e5",
                "legacy_public_message": legacy,
                "coverage_candidates": [{
                    "subject_kind": "craft", "subject_id": "灰塑",
                    "source_ids": ["S1"], "evidence_kind": "craft_overview",
                    "node_id": "front",
                }],
                "narration_render_audit": {
                    "node_id": "front", "rendered_craft_ids": ["灰塑"],
                    "rendered_ornament_ids": [], "used_source_ids": ["S1"],
                },
            },
            "role_narration_candidate": {
                "schema_version": "role_narration_candidate_v1",
                "generation_status": "generated", "reason_code": None,
                "style_id": "ancient_scholar",
                "public_text": "诸位且看，屋脊可见灰塑。",
                "used_fact_ids": ["craft:灰塑"], "omitted_fact_ids": [],
                "self_check": {"added_new_facts": False, "role_consistent": True, "within_budget": True},
                "model_called": True, "latency_ms": 20,
            },
            "narration_validation": {"validation_status": "accepted", "reason_codes": []},
            "active_role_narration_audit": {"mode": "active", "style_id": "ancient_scholar"},
            "tour_presentation": {"message": legacy, "ok": True},
        }

    @staticmethod
    def active_environment():
        return patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
        }, clear=False)

    def test_active_validation_routes_to_unique_commit(self):
        with self.active_environment():
            self.assertEqual(route_after_narration_validation(self.state()), "narration_commit")
        state = self.state()
        result = narration_commit_node(state)
        self.assertEqual(result["messages"][0].id, "legacy-message")
        self.assertIn("诸位且看", result["messages"][0].content)
        self.assertIn("【下一步】", result["messages"][0].content)
        self.assertEqual(result["narration_coverage"]["introduced_craft_ids"], ["灰塑"])
        self.assertIsNone(result["pending_role_narration_commit"])
        self.assertNotIn("tour_state", result)
        self.assertNotIn("visitor_profile", result)
        self.assertTrue(result["active_role_narration_audit"]["active_takeover"])

    def test_rejected_active_candidate_routes_to_deterministic_fallback(self):
        state = self.state()
        state["narration_validation"] = {"validation_status": "rejected", "reason_codes": ["unsafe"]}
        with self.active_environment():
            self.assertEqual(route_after_narration_validation(state), "deterministic_narration_fallback")
        result = deterministic_narration_fallback_node(state)
        self.assertEqual(result["narration_coverage"]["introduced_craft_ids"], ["灰塑"])
        self.assertIsNone(result["pending_role_narration_commit"])
        self.assertFalse(result["active_role_narration_audit"]["active_takeover"])
        self.assertTrue(result["active_role_narration_audit"]["legacy_message_preserved"])
        self.assertNotIn("messages", result)

    def test_shadow_never_routes_to_takeover(self):
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
        }, clear=False):
            self.assertEqual(route_after_narration_validation(self.state()), "atomic_read_plan_shadow")

    def test_role_failure_injection_is_isolated_from_global_model_key(self):
        with patch.dict(os.environ, {"CJC_ROLE_NARRATION_TEST_FAILURE": "invalid_json"}, clear=False):
            self.assertEqual(
                _invoke_role_narration_model("ignored"), "{injected-invalid-json"
            )
        with patch.dict(os.environ, {"CJC_ROLE_NARRATION_TEST_FAILURE": "timeout"}, clear=False):
            with self.assertRaises(TimeoutError):
                _invoke_role_narration_model("ignored")

    def test_budget_exceeded_injection_fails_closed_in_role_layer_only(self):
        state = self.state()
        state["visitor_profile"] = {"language": "zh"}
        state["active_route_plan"] = {"route_id": "unchanged"}
        state["role_mode_shadow"] = {
            "status": "selected", "selected_style_id": "listen_only",
            "source": "visitor_profile", "confidence": 1.0,
        }
        state["narration_content_plan"] = NarrationContentPlan(
            stop_id="front", style_id="listen_only", language="zh",
            budget_seconds=60,
            allocated_content_seconds=50,
            facts=(NarrationFact(
                "craft:灰塑", "craft_background", "屋脊可见灰塑。",
            ),),
            must_include=("space_or_object_identity",),
            already_covered=(), must_not_claim=(), interaction_allowed=False,
        ).to_dict()
        coverage_before = dict(state["narration_coverage"])
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
            "CJC_ROLE_NARRATION_TEST_FAILURE": "budget_exceeded",
        }, clear=False):
            generated = role_narration_generation_node(state)
            validated = narration_validation_node({**state, **generated})

        self.assertGreater(
            generated["narration_content_plan"]["allocated_content_seconds"],
            generated["narration_content_plan"]["budget_seconds"],
        )
        self.assertEqual(
            generated["role_narration_candidate"]["reason_code"],
            "budget_exceeded",
        )
        self.assertFalse(generated["role_narration_candidate"]["model_called"])
        audit = validated["active_role_narration_audit"]
        self.assertEqual(audit["validation_status"], "rejected")
        self.assertIn("budget_exceeded", audit["reason_codes"])
        self.assertFalse(audit["within_budget"])
        self.assertFalse(audit["public_message_safe"])
        self.assertFalse(audit["active_takeover"])
        self.assertTrue(audit["fallback_used"])
        self.assertTrue(audit["legacy_message_preserved"])
        self.assertTrue(audit["same_public_message"])
        self.assertEqual(audit["state_writes"], [])
        self.assertNotIn("messages", generated)
        self.assertNotIn("messages", validated)
        self.assertNotIn("tour_state", generated)
        self.assertNotIn("visitor_profile", generated)
        self.assertNotIn("active_route_plan", generated)
        self.assertNotIn("narration_coverage", generated)
        self.assertNotIn("narration_coverage", validated)
        self.assertEqual(state["narration_coverage"], coverage_before)

    def test_role_model_text_content_blocks_are_decoded_without_stringifying(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "test-key",
            "CJC_ROLE_NARRATION_TEST_FAILURE": "",
            "ROLE_NARRATION_MAX_TOKENS": "4096",
        }, clear=False), patch("agent_graph.ChatDeepSeek") as model_cls:
            response = model_cls.return_value.invoke.return_value
            response.response_metadata = {"finish_reason": "stop"}
            response.content = [
                {"type": "text", "text": '{"schema_version":"role_narration_candidate_v1"}'},
            ]
            self.assertEqual(
                _invoke_role_narration_model("ignored"),
                '{"schema_version":"role_narration_candidate_v1"}',
            )
            model_cls.assert_called_once_with(
                model=os.getenv("ROLE_NARRATION_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")),
                temperature=0,
                max_tokens=4096,
                extra_body={
                    "thinking": {"type": "disabled"},
                    "response_format": {"type": "json_object"},
                },
            )
            self.assertFalse(model_cls.return_value.bind.called)

    def test_role_model_length_finish_reason_fails_closed_without_partial_json(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "test-key",
            "CJC_ROLE_NARRATION_TEST_FAILURE": "",
            "ROLE_NARRATION_MAX_TOKENS": "4096",
        }, clear=False), patch("agent_graph.ChatDeepSeek") as model_cls:
            response = model_cls.return_value.invoke.return_value
            response.response_metadata = {"finish_reason": "length"}
            response.content = '{"schema_version":"role_narration_candidate_v1"'
            with self.assertRaisesRegex(RuntimeError, "role_narration_output_truncated"):
                _invoke_role_narration_model("ignored")

    def test_role_model_rejects_unsafe_token_budget_configuration(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "test-key",
            "CJC_ROLE_NARRATION_TEST_FAILURE": "",
            "ROLE_NARRATION_MAX_TOKENS": "99999",
        }, clear=False):
            with self.assertRaisesRegex(ValueError, "between 512 and 8192"):
                _invoke_role_narration_model("ignored")

    def test_invalid_internal_envelope_writes_no_tour_state_or_profile(self):
        state = self.state()
        state["role_narration_candidate"]["state_patch"] = {
            "tour_state": {"current_stop_id": "forged"},
            "visitor_profile": {"language": "en"},
        }
        result = narration_validation_node(state)
        self.assertEqual(result["narration_validation"]["validation_status"], "rejected")
        self.assertNotIn("tour_state", result)
        self.assertNotIn("visitor_profile", result)
        self.assertNotIn("active_route_plan", result)


if __name__ == "__main__":
    unittest.main()
