from __future__ import annotations

from copy import deepcopy
import unittest

from controlled_executor import execute_approved_read_tool, validate_read_result
from policy_gate import GateVerdict
from reviewed_read_tools import ReadToolResult


def _result(**changes):
    value = ReadToolResult("single_fact", "ok", "陈家祠于1888年开始筹建。", ({"source_ids": ["S02"]},), {"source_ids": ["S02"]})
    return changes.get("result", value)


class ControlledExecutorTests(unittest.TestCase):
    VERDICT = GateVerdict(True, "approved", "reviewed_single_fact", ("reviewed_category", "registered_source"))
    def test_rejected_gate_never_calls_backend(self):
        result = execute_approved_read_tool(GateVerdict(False, "evidence_missing"), {}, {"reviewed_single_fact": lambda _: self.fail("must not run")})
        self.assertEqual((result.status, result.audit_reason), ("not_executed", "evidence_missing"))
    def test_executes_once_with_copied_payload_and_validates_public_evidence(self):
        payload, before, calls = {"nested": {"x": 1}}, {"nested": {"x": 1}}, []
        def backend(value):
            calls.append(value); value["nested"]["x"] = 2; return _result()
        result = execute_approved_read_tool(self.VERDICT, payload, {"reviewed_single_fact": backend})
        self.assertEqual(result.status, "ok"); self.assertEqual(len(calls), 1); self.assertEqual(payload, before)
    def test_failure_and_invalid_results_fail_closed(self):
        failed = execute_approved_read_tool(self.VERDICT, {}, {"reviewed_single_fact": lambda _: (_ for _ in ()).throw(RuntimeError())})
        bad = ReadToolResult("single_fact", "ok", "source_ids: S02", (), {})
        invalid = execute_approved_read_tool(self.VERDICT, {}, {"reviewed_single_fact": lambda _: bad})
        self.assertEqual(failed.status, "tool_unavailable")
        self.assertEqual((invalid.status, invalid.audit_reason), ("result_rejected", "visitor_message_rejected"))
    def test_capability_and_evidence_contracts_are_enforced(self):
        self.assertEqual(validate_read_result("reviewed_single_fact", ReadToolResult("term", "ok", "安全正文", ({},), {})), "result_capability_mismatch")
        self.assertEqual(validate_read_result("reviewed_single_fact", ReadToolResult("single_fact", "ok", "安全正文", (), {})), "evidence_missing")


if __name__ == "__main__": unittest.main()
