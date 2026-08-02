"""CA-07 one-shot executor and result validator for approved read-only tools."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Any, Callable, Mapping

from controlled_knowledge_query import is_public_visitor_message
from policy_gate import GateVerdict
from reviewed_read_tools import ReadToolResult
from tool_registry import get_tool


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    result: ReadToolResult | None
    audit_reason: str


def validate_read_payload(tool_name: str, payload: Mapping[str, Any]) -> str | None:
    """Reject missing, unknown, or non-mapping inputs before backend invocation."""
    try:
        spec = get_tool(tool_name)
    except Exception:
        return "tool_unregistered"
    if not isinstance(payload, Mapping):
        return "input_type_rejected"
    keys = set(payload)
    required = set(spec.input_schema.required_fields)
    allowed = required | set(spec.input_schema.optional_fields)
    if not required.issubset(keys):
        return "input_schema_missing"
    if not keys.issubset(allowed):
        return "input_schema_rejected"
    if not isinstance(payload.get("user_text"), str) or not payload["user_text"].strip():
        return "input_value_rejected"
    if "evidence" in payload and not isinstance(payload["evidence"], (list, tuple)):
        return "input_value_rejected"
    return None


def validate_read_result(tool_name: str, result: object) -> str | None:
    """Return a rejection reason, keeping internal detail out of visitor output."""
    if not isinstance(result, ReadToolResult):
        return "result_type_rejected"
    try:
        spec = get_tool(tool_name)
    except Exception:
        return "tool_unregistered"
    if result.capability != spec.capability:
        return "result_capability_mismatch"
    if not isinstance(result.status, str) or not result.status:
        return "output_schema_rejected"
    if not isinstance(result.message, str) or not result.message or not is_public_visitor_message(result.message):
        return "visitor_message_rejected"
    if not isinstance(result.evidence, tuple) or not all(isinstance(item, Mapping) for item in result.evidence):
        return "output_schema_rejected"
    if not isinstance(result.audit, Mapping):
        return "output_schema_rejected"
    if result.status == "ok" and not result.evidence and not result.audit.get("source_ids"):
        return "evidence_missing"
    evidence_sources = {
        source for item in result.evidence for source in item.get("source_ids", ())
        if isinstance(source, str) and source
    }
    audit_sources = result.audit.get("source_ids", ())
    if isinstance(audit_sources, (str, bytes)) or not isinstance(audit_sources, (list, tuple, set)):
        return "output_schema_rejected"
    if any(not isinstance(source, str) or not source for source in audit_sources):
        return "output_schema_rejected"
    if audit_sources and not set(audit_sources).issubset(evidence_sources):
        return "evidence_source_conflict"
    return None


def execute_approved_read_tool(
    verdict: GateVerdict, payload: Mapping[str, Any],
    executors: Mapping[str, Callable[[dict[str, Any]], ReadToolResult]],
) -> ExecutionResult:
    """Invoke one approved adapter once; rejected paths never invoke a backend."""
    if not verdict.approved or not verdict.tool_name:
        return ExecutionResult("not_executed", None, verdict.reason)
    try:
        spec = get_tool(verdict.tool_name)
    except Exception:
        return ExecutionResult("not_executed", None, "tool_unregistered")
    executor = executors.get(spec.tool_name)
    if executor is None:
        return ExecutionResult("tool_unavailable", None, "executor_unavailable")
    input_reason = validate_read_payload(spec.tool_name, payload)
    if input_reason:
        return ExecutionResult("not_executed", None, input_reason)
    started = time.perf_counter()
    try:
        result = executor(deepcopy(dict(payload)))
    except Exception:
        return ExecutionResult("tool_unavailable", None, "executor_failed")
    if (time.perf_counter() - started) * 1000 > spec.timeout_ms:
        return ExecutionResult("tool_unavailable", None, "executor_timeout")
    reason = validate_read_result(spec.tool_name, result)
    if reason:
        return ExecutionResult("result_rejected", None, reason)
    return ExecutionResult("ok", result, "approved_result")
