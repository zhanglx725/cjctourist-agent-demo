from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import time
import unittest
from unittest.mock import patch

from controlled_executor import execute_approved_read_tool, validate_read_payload, validate_read_result
from policy_gate import GateVerdict
from reviewed_read_tools import ReadToolResult
from tool_registry import get_tool


def _result(**changes):
    value = ReadToolResult("single_fact", "ok", "陈家祠于1888年开始筹建。", ({"source_ids": ["S02"]},), {"source_ids": ["S02"]})
    return changes.get("result", value)


class ControlledExecutorTests(unittest.TestCase):
    VERDICT = GateVerdict(True, "approved", "reviewed_single_fact", ("reviewed_category", "registered_source"))
    def test_rejected_gate_never_calls_backend(self):
        result = execute_approved_read_tool(GateVerdict(False, "evidence_missing"), {}, {"reviewed_single_fact": lambda _: self.fail("must not run")})
        self.assertEqual((result.status, result.audit_reason), ("not_executed", "evidence_missing"))
    def test_executes_once_with_copied_payload_and_validates_public_evidence(self):
        payload, before, calls = {"user_text": "陈家祠什么时候开始筹建？", "evidence": [], "nested": {"x": 1}}, {"user_text": "陈家祠什么时候开始筹建？", "evidence": [], "nested": {"x": 1}}, []
        def backend(value):
            calls.append(value); value["nested"]["x"] = 2; return _result()
        # Unknown input fields fail closed before a backend can observe them.
        self.assertEqual(validate_read_payload("reviewed_single_fact", payload), "input_schema_rejected")
        payload = {"user_text": "陈家祠什么时候开始筹建？", "evidence": []}
        before = deepcopy(payload)
        def backend(value):
            calls.append(value); value["evidence"].append({"x": 2}); return _result()
        result = execute_approved_read_tool(self.VERDICT, payload, {"reviewed_single_fact": backend})
        self.assertEqual(result.status, "ok"); self.assertEqual(len(calls), 1); self.assertEqual(payload, before)
    def test_failure_and_invalid_results_fail_closed(self):
        payload = {"user_text": "陈家祠什么时候开始筹建？"}
        failed = execute_approved_read_tool(self.VERDICT, payload, {"reviewed_single_fact": lambda _: (_ for _ in ()).throw(RuntimeError())})
        bad = ReadToolResult("single_fact", "ok", "source_ids: S02", (), {})
        invalid = execute_approved_read_tool(self.VERDICT, payload, {"reviewed_single_fact": lambda _: bad})
        self.assertEqual(failed.status, "tool_unavailable")
        self.assertEqual((invalid.status, invalid.audit_reason), ("result_rejected", "visitor_message_rejected"))
    def test_capability_and_evidence_contracts_are_enforced(self):
        self.assertEqual(validate_read_result("reviewed_single_fact", ReadToolResult("term", "ok", "安全正文", ({},), {})), "result_capability_mismatch")
        self.assertEqual(validate_read_result("reviewed_single_fact", ReadToolResult("single_fact", "ok", "安全正文", (), {})), "evidence_missing")

    def test_input_output_conflict_and_timeout_fail_closed(self):
        self.assertEqual(validate_read_payload("reviewed_single_fact", {}), "input_schema_missing")
        self.assertEqual(validate_read_payload("reviewed_single_fact", {"user_text": "x", "state_update": {}}), "input_schema_rejected")
        conflict = ReadToolResult("single_fact", "ok", "安全正文", ({"source_ids": ["S01"]},), {"source_ids": ["S02"]})
        self.assertEqual(validate_read_result("reviewed_single_fact", conflict), "evidence_source_conflict")
        malformed = ReadToolResult("single_fact", "", "安全正文", ({},), {})
        self.assertEqual(validate_read_result("reviewed_single_fact", malformed), "output_schema_rejected")
        tiny_timeout = replace(get_tool("reviewed_single_fact"), timeout_ms=1)
        with patch("controlled_executor.get_tool", return_value=tiny_timeout):
            timeout = execute_approved_read_tool(
                self.VERDICT, {"user_text": "陈家祠什么时候开始筹建？"},
                {"reviewed_single_fact": lambda _: time.sleep(0.01) or _result()},
            )
        self.assertEqual((timeout.status, timeout.audit_reason), ("tool_unavailable", "executor_timeout"))


if __name__ == "__main__": unittest.main()
