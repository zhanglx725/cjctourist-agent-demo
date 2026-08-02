"""CA-07 one-shot executor and result validator for approved read-only tools."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
    if not result.message or not is_public_visitor_message(result.message):
        return "visitor_message_rejected"
    if result.status == "ok" and not result.evidence and not result.audit.get("source_ids"):
        return "evidence_missing"
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
    try:
        result = executor(deepcopy(dict(payload)))
    except Exception:
        return ExecutionResult("tool_unavailable", None, "executor_failed")
    reason = validate_read_result(spec.tool_name, result)
    if reason:
        return ExecutionResult("result_rejected", None, reason)
    return ExecutionResult("ok", result, "approved_result")
