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
from narration_service_tail import (
    COMPLETION_PROMPT,
    build_stop_service_tail,
    compose_stop_presentation,
)
from route_planner import plan_template
from tour_state import start_tour


class RoleNarrationGraphTests(unittest.TestCase):
    STOP_ID = "stop_front_courtyard_center"

    def state(self):
        legacy = "【工艺背景：灰塑】\n\n屋脊可见灰塑。\n\n【下一步】\n\n讲解结束后可继续。"
        tour_state = start_tour(plan_template("highlights_30"))
        tour_state["current_stop_id"] = self.STOP_ID
        service_tail = build_stop_service_tail(tour_state=tour_state)
        candidate_text = "诸位且看，屋脊可见灰塑。"
        return {
            "messages": [AIMessage(id="legacy-message", content=legacy, additional_kwargs={"stop_guidance": True})],
            "tour_state": tour_state,
            "narration_coverage": empty_narration_coverage().to_dict(),
            "pending_role_narration_commit": {
                "status": "guided_e5",
                "legacy_public_message": legacy,
                "coverage_candidates": [{
                    "subject_kind": "craft", "subject_id": "灰塑",
                    "source_ids": ["S1"], "evidence_kind": "craft_overview",
                    "node_id": self.STOP_ID,
                }],
                "narration_render_audit": {
                    "node_id": self.STOP_ID, "rendered_craft_ids": ["灰塑"],
                    "rendered_ornament_ids": [], "used_source_ids": ["S1"],
                },
                "service_tail": service_tail.to_dict(),
            },
            "role_narration_candidate": {
                "schema_version": "role_narration_candidate_v1",
                "generation_status": "generated", "reason_code": None,
                "style_id": "ancient_scholar",
                "public_text": candidate_text,
                "used_fact_ids": ["craft:灰塑"], "omitted_fact_ids": [],
                "self_check": {"added_new_facts": False, "role_consistent": True, "within_budget": True},
                "model_called": True, "latency_ms": 20,
            },
            "narration_validation": {
                "validation_status": "accepted", "reason_codes": [],
                "service_tail_validation": {
                    "validation_status": "accepted", "reason_codes": [],
                },
                "validated_public_message": compose_stop_presentation(
                    candidate_text,
                    " ".join(unit.public_text for unit in service_tail.units),
                ),
            },
            "active_role_narration_audit": {"mode": "active", "style_id": "ancient_scholar"},
            "tour_presentation": {"message": legacy, "ok": True},
        }

    @staticmethod
    def active_environment():
        return patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
            "ROLE_ACTIVE_ENABLED": "true",
            "ROLE_ACTIVE_STYLES": "neutral,child,ancient_scholar",
            "ROLE_ACTIVE_SCENES": "route_planning,route_opening,stop_guidance",
        }, clear=False)

    def state_with_plan(self, style_id="ancient_scholar"):
        state = self.state()
        state["visitor_profile"] = {"language": "zh"}
        state["role_mode_shadow"] = {
            "status": "selected", "selected_style_id": style_id,
            "source": "visitor_profile", "confidence": 1.0,
        }
        state["narration_content_plan"] = NarrationContentPlan(
            stop_id=self.STOP_ID, style_id=style_id, language="zh",
            budget_seconds=60, allocated_content_seconds=20,
            facts=(NarrationFact(
                "craft:灰塑", "craft_background", "屋脊可见灰塑。",
            ),),
            must_include=("space_or_object_identity",),
            already_covered=(), must_not_claim=(),
            interaction_allowed=style_id != "listen_only",
        ).to_dict()
        state.pop("role_narration_candidate", None)
        state.pop("narration_validation", None)
        state.pop("active_role_narration_audit", None)
        return state

    def assert_active_failure_falls_back_once(self, state, expected_reason):
        validated = narration_validation_node(state)
        audit = validated["active_role_narration_audit"]
        self.assertEqual(audit["validation_status"], "rejected")
        self.assertIn(expected_reason, audit["reason_codes"])
        merged = {**state, **validated}
        self.assertEqual(
            route_after_narration_validation(merged),
            "deterministic_narration_fallback",
        )
        fallback = deterministic_narration_fallback_node(merged)
        self.assertFalse(fallback["active_role_narration_audit"]["active_takeover"])
        self.assertTrue(fallback["active_role_narration_audit"]["fallback_used"])
        self.assertTrue(fallback["active_role_narration_audit"]["legacy_message_preserved"])
        self.assertEqual(
            fallback["narration_coverage"]["introduced_craft_ids"],
            ["灰塑"],
        )
        self.assertEqual(fallback["active_role_narration_audit"]["state_writes"], [])
        self.assertNotIn("messages", fallback)
        second = deterministic_narration_fallback_node({**merged, **fallback})
        self.assertEqual(
            second["narration_coverage"]["introduced_craft_ids"],
            ["灰塑"],
        )

    def test_active_validation_routes_to_unique_commit(self):
        with self.active_environment():
            self.assertEqual(route_after_narration_validation(self.state()), "narration_commit")
            state = self.state()
            result = narration_commit_node(state)
        self.assertEqual(result["messages"][0].id, "legacy-message")
        self.assertIn("诸位且看", result["messages"][0].content)
        self.assertIn(COMPLETION_PROMPT, result["messages"][0].content)
        self.assertIn("完成本点后，下一站：月台", result["messages"][0].content)
        self.assertNotIn("【下一步】", result["messages"][0].content)
        self.assertNotIn("【工艺背景", result["messages"][0].content)
        self.assertEqual(result["narration_coverage"]["introduced_craft_ids"], ["灰塑"])
        self.assertIsNone(result["pending_role_narration_commit"])
        self.assertNotIn("tour_state", result)
        self.assertNotIn("visitor_profile", result)
        self.assertTrue(result["active_role_narration_audit"]["active_takeover"])
        self.assertEqual(
            result["active_role_narration_audit"]["commit_decision"],
            "role_candidate_published",
        )
        self.assertEqual(
            result["active_role_narration_audit"]["commit_validation_status"],
            "accepted",
        )

    def test_stop_guidance_active_commit_is_limited_to_three_styles(self):
        with self.active_environment():
            for style_id in ("neutral", "child", "ancient_scholar"):
                with self.subTest(style_id=style_id):
                    state = self.state()
                    state["role_narration_candidate"]["style_id"] = style_id
                    state["active_role_narration_audit"]["style_id"] = style_id
                    result = narration_commit_node(state)
                    self.assertTrue(result["active_role_narration_audit"]["active_takeover"])
                    self.assertFalse(result["active_role_narration_audit"]["fallback_used"])
                    self.assertIsNone(result["pending_role_narration_commit"])
                    self.assertEqual(
                        result["narration_coverage"]["introduced_craft_ids"],
                        ["灰塑"],
                    )

            denied = self.state()
            denied["role_narration_candidate"]["style_id"] = "dominant_ceo"
            denied["active_role_narration_audit"]["style_id"] = "dominant_ceo"
            result = narration_commit_node(denied)
            self.assertFalse(result["active_role_narration_audit"]["active_takeover"])
            self.assertTrue(result["active_role_narration_audit"]["fallback_used"])
            self.assertTrue(result["active_role_narration_audit"]["legacy_message_preserved"])
            self.assertNotIn("messages", result)

    def test_stop_guidance_kill_switch_blocks_direct_commit(self):
        state = self.state()
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
            "ROLE_ACTIVE_ENABLED": "false",
            "ROLE_ACTIVE_STYLES": "neutral,child,ancient_scholar",
            "ROLE_ACTIVE_SCENES": "route_planning,route_opening,stop_guidance",
        }, clear=False):
            result = narration_commit_node(state)
        self.assertFalse(result["active_role_narration_audit"]["active_takeover"])
        self.assertTrue(result["active_role_narration_audit"]["fallback_used"])
        self.assertTrue(result["active_role_narration_audit"]["legacy_message_preserved"])
        self.assertEqual(
            result["active_role_narration_audit"]["commit_decision"],
            "legacy_fallback_published",
        )
        self.assertEqual(
            result["active_role_narration_audit"]["commit_validation_status"],
            "accepted",
        )
        self.assertNotIn("messages", result)

    def test_validation_audit_records_style_quality_without_changing_commit_authority(self):
        state = self.state_with_plan()
        state["role_narration_candidate"] = {
            **self.state()["role_narration_candidate"],
            "public_text": "请看，屋脊可见灰塑。",
        }
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
            "ROLE_ACTIVE_ENABLED": "true",
            "ROLE_ACTIVE_STYLES": "ancient_scholar",
            "ROLE_ACTIVE_SCENES": "stop_guidance",
        }, clear=False):
            result = narration_validation_node(state)
        audit = result["active_role_narration_audit"]
        self.assertFalse(audit["style_quality_passed"])
        self.assertIn("style_coverage_incomplete", audit["style_quality_reason_codes"])
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "read_only_active",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
            "ROLE_ACTIVE_ENABLED": "true",
            "ROLE_ACTIVE_STYLES": "ancient_scholar",
            "ROLE_ACTIVE_SCENES": "stop_guidance",
        }, clear=False):
            self.assertEqual(
                route_after_narration_validation({**state, **result}),
                "deterministic_narration_fallback",
            )

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

    def test_missing_service_tail_is_rejected_before_commit(self):
        state = self.state_with_plan()
        state["role_narration_candidate"] = self.state()["role_narration_candidate"]
        state["pending_role_narration_commit"].pop("service_tail")
        with self.active_environment():
            validated = narration_validation_node(state)
            next_node = route_after_narration_validation({**state, **validated})
        self.assertEqual(
            validated["narration_validation"]["validation_status"], "rejected",
        )
        self.assertIn(
            "service_tail_missing",
            validated["narration_validation"]["reason_codes"],
        )
        self.assertFalse(validated["active_role_narration_audit"]["service_tail_passed"])
        self.assertEqual(next_node, "deterministic_narration_fallback")

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

    def test_active_timeout_and_invalid_json_fall_back_to_legacy_once(self):
        with self.active_environment():
            for failure, expected_prefix in (
                ("timeout", "model_unavailable"),
                ("invalid_json", "invalid_candidate_schema"),
            ):
                with self.subTest(failure=failure), patch.dict(
                    os.environ,
                    {"CJC_ROLE_NARRATION_TEST_FAILURE": failure},
                    clear=False,
                ):
                    state = self.state_with_plan()
                    generated = role_narration_generation_node(state)
                    candidate = generated["role_narration_candidate"]
                    self.assertEqual(candidate["generation_status"], "rejected")
                    reason = str(candidate.get("reason_code") or "")
                    self.assertTrue(reason.startswith(expected_prefix), reason)
                    self.assert_active_failure_falls_back_once(
                        {**state, **generated}, reason,
                    )

    def test_active_fact_drift_and_internal_leak_fall_back_to_legacy_once(self):
        with self.active_environment():
            for public_text, used_ids, expected_reason in (
                ("屋脊可见灰塑。", ["fact:unknown"], "fact_id_boundary_violation"),
                ("屋脊可见灰塑。source_ids=S1", ["craft:灰塑"], "internal_field_leak"),
            ):
                with self.subTest(expected_reason=expected_reason):
                    state = self.state_with_plan()
                    state["role_narration_candidate"] = {
                        "schema_version": "role_narration_candidate_v1",
                        "generation_status": "generated", "reason_code": None,
                        "style_id": "ancient_scholar", "public_text": public_text,
                        "used_fact_ids": used_ids, "omitted_fact_ids": [],
                        "self_check": {
                            "added_new_facts": False,
                            "role_consistent": True,
                            "within_budget": True,
                        },
                        "model_called": True, "latency_ms": 1,
                    }
                    self.assert_active_failure_falls_back_once(state, expected_reason)

    def test_budget_exceeded_injection_fails_closed_in_role_layer_only(self):
        state = self.state()
        state["visitor_profile"] = {"language": "zh"}
        state["active_route_plan"] = {"route_id": "unchanged"}
        state["role_mode_shadow"] = {
            "status": "selected", "selected_style_id": "ancient_scholar",
            "source": "visitor_profile", "confidence": 1.0,
        }
        state["narration_content_plan"] = NarrationContentPlan(
            stop_id="front", style_id="ancient_scholar", language="zh",
            budget_seconds=60,
            allocated_content_seconds=50,
            facts=(NarrationFact(
                "craft:灰塑", "craft_background", "屋脊可见灰塑。",
            ),),
            must_include=("space_or_object_identity",),
            already_covered=(), must_not_claim=(), interaction_allowed=True,
        ).to_dict()
        coverage_before = dict(state["narration_coverage"])
        with self.active_environment(), patch.dict(os.environ, {
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
        merged = {**state, **generated, **validated}
        with self.active_environment():
            self.assertEqual(
                route_after_narration_validation(merged),
                "deterministic_narration_fallback",
            )
            fallback = deterministic_narration_fallback_node(merged)
        self.assertEqual(
            fallback["narration_coverage"]["introduced_craft_ids"],
            ["灰塑"],
        )

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
                timeout=45.0,
                max_retries=0,
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
