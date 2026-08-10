"""CA-02 metadata-only registry for approved read-only capabilities.

This registry declares contracts only.  It neither imports a business backend
nor executes a tool, so reviewed facts, route state, and existing routing stay
outside this phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class RuntimePhase(StrEnum):
    PRE_TOUR = "pre_tour"
    TOURING = "touring"
    EXPLAINING = "explaining"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class RegistrySideEffect(StrEnum):
    READ_ONLY = "read_only"
    PROPOSAL_ONLY = "proposal_only"
    CONFIRMED_STATE_CHANGE = "confirmed_state_change"
    PROHIBITED = "prohibited"


class FailurePolicy(StrEnum):
    FAIL_CLOSED = "fail_closed"
    SAFE_UNAVAILABLE = "safe_unavailable"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class SchemaSpec:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    version: str
    capability: str
    input_schema: SchemaSpec
    output_schema: SchemaSpec
    allowed_phases: tuple[RuntimePhase, ...]
    evidence_requirements: tuple[str, ...]
    side_effect_level: RegistrySideEffect
    requires_confirmation: bool
    timeout_ms: int
    max_calls_per_turn: int
    failure_policy: FailurePolicy
    visitor_fields: tuple[str, ...]
    audit_fields: tuple[str, ...]


class ToolRegistryError(ValueError):
    pass


class UnknownToolError(ToolRegistryError):
    pass


_ALL_PHASES = tuple(RuntimePhase)
_PUBLIC_FIELDS = ("message", "status", "items")
_AUDIT_FIELDS = ("evidence", "source_ids", "retrieval_strategy", "audit_reason")


def _spec(
    tool_name: str,
    capability: str,
    *,
    input_fields: tuple[str, ...] = ("user_text",),
    optional_input_fields: tuple[str, ...] = ("tour_context", "evidence"),
    output_fields: tuple[str, ...] = ("message", "status"),
    evidence: tuple[str, ...] = ("reviewed_evidence",),
    failure: FailurePolicy = FailurePolicy.FAIL_CLOSED,
) -> ToolSpec:
    return ToolSpec(
        tool_name=tool_name,
        version="v1",
        capability=capability,
        input_schema=SchemaSpec(input_fields, optional_input_fields),
        output_schema=SchemaSpec(output_fields, ("evidence", "source_ids", "retrieval_strategy")),
        allowed_phases=_ALL_PHASES,
        evidence_requirements=evidence,
        side_effect_level=RegistrySideEffect.READ_ONLY,
        requires_confirmation=False,
        timeout_ms=3_000,
        max_calls_per_turn=1,
        failure_policy=failure,
        visitor_fields=_PUBLIC_FIELDS,
        audit_fields=_AUDIT_FIELDS,
    )


DEFAULT_TOOL_SPECS: tuple[ToolSpec, ...] = (
    _spec("reviewed_single_fact", "single_fact", evidence=("reviewed_category", "registered_source")),
    _spec("reviewed_visit_service", "visit_service", evidence=("reviewed_service_rule", "validity_checked")),
    _spec("reviewed_controlled_knowledge", "controlled_knowledge", evidence=("closed_category", "registered_source")),
    _spec("reviewed_term", "term", evidence=("runtime_eligibility", "registered_source")),
    _spec("reviewed_craft", "craft", evidence=("canonical_craft_section",)),
    _spec("reviewed_ornament", "object", evidence=("reviewed_ornament", "node_object_evidence_same_source")),
    _spec("reviewed_point_inventory", "point_inventory", evidence=("reviewed_node", "inventory_whitelist")),
    _spec("reviewed_research", "research", evidence=("research_intent", "attributed_research_card")),
    _spec("reviewed_comparison", "comparison", evidence=("comparison_eligibility", "attributed_comparison_card")),
    _spec("reviewed_photo", "photo", evidence=("photo_eligibility", "safety_checked"), failure=FailurePolicy.CLARIFICATION),
    _spec("reviewed_navigation", "navigation", evidence=("formal_route", "reviewed_node"), failure=FailurePolicy.SAFE_UNAVAILABLE),
)


def validate_registry(specs: Iterable[ToolSpec]) -> tuple[ToolSpec, ...]:
    """Validate metadata eagerly; invalid/duplicate registrations fail closed."""
    values = tuple(specs)
    if not values:
        raise ToolRegistryError("registry_must_not_be_empty")
    names: set[str] = set()
    capabilities: set[str] = set()
    for spec in values:
        if not spec.tool_name or not spec.version or not spec.capability:
            raise ToolRegistryError("identity_missing")
        if spec.tool_name in names or spec.capability in capabilities:
            raise ToolRegistryError("duplicate_registration")
        names.add(spec.tool_name)
        capabilities.add(spec.capability)
        if not spec.input_schema.required_fields or not spec.output_schema.required_fields:
            raise ToolRegistryError("schema_incomplete")
        if set(spec.input_schema.required_fields) & set(spec.input_schema.optional_fields):
            raise ToolRegistryError("input_schema_overlap")
        if not spec.allowed_phases or not spec.evidence_requirements:
            raise ToolRegistryError("eligibility_missing")
        if spec.side_effect_level is not RegistrySideEffect.READ_ONLY or spec.requires_confirmation:
            raise ToolRegistryError("non_read_only_tool_rejected")
        if spec.timeout_ms <= 0 or spec.max_calls_per_turn != 1:
            raise ToolRegistryError("execution_limits_rejected")
        if not set(spec.visitor_fields).issubset(_PUBLIC_FIELDS):
            raise ToolRegistryError("visitor_fields_rejected")
        if not set(spec.audit_fields).issubset(_AUDIT_FIELDS):
            raise ToolRegistryError("audit_fields_rejected")
        if set(spec.visitor_fields) & set(spec.audit_fields):
            raise ToolRegistryError("visitor_audit_leakage")
    return values


REGISTERED_TOOLS = validate_registry(DEFAULT_TOOL_SPECS)
_BY_NAME = {spec.tool_name: spec for spec in REGISTERED_TOOLS}
_BY_CAPABILITY = {spec.capability: spec for spec in REGISTERED_TOOLS}


def get_tool(tool_name: str) -> ToolSpec:
    """Return an approved spec; unknown names are rejected by default."""
    try:
        return _BY_NAME[tool_name]
    except KeyError as exc:
        raise UnknownToolError("unregistered_tool") from exc


def get_capability(capability: str) -> ToolSpec:
    try:
        return _BY_CAPABILITY[capability]
    except KeyError as exc:
        raise UnknownToolError("unregistered_capability") from exc
