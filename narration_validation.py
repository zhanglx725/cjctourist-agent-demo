"""Deterministic validation for role narration candidates."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from controlled_knowledge_query import public_visitor_message_or_fallback
from narration_content_plan import NarrationContentPlan
from narration_style_policy import StyleBrief
from role_narration_generation import (
    UNAPPROVED_CONNECTOR_FACT_TRIGGER,
    RoleNarrationCandidate,
    role_connector_character_limit,
    role_connector_text,
)


_INTERNAL = re.compile(
    r"(?:https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|node[_ ]?id|raw[_ ]?chunk|"
    r"rag_tool|llm_think|stop_guidance|narration_content_plan)", re.IGNORECASE
)
_DANGEROUS = re.compile(r"(?:触摸|攀爬|攀坐|跨越护栏|堵住通道|必须回答|强制互动)")
_INTERACTION_REQUEST = re.compile(r"(?:\?|？|请你|试着|任务|回答|拍照|跟着做)")
_SENTENCE_LIMITS = {"short": 42, "compact": 60, "medium": 80}
_MALFORMED_PUNCTUATION = re.compile(r"(?:[。！？]{2,}|[，、]{2,}|[，。！？]\s*[，。！？]|～)")
_LAYOUT_HEADING = re.compile(r"【[^】]+】")
_LAYOUT_MARKDOWN = re.compile(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s+)")
# A single blank line is the approved semantic paragraph boundary.  Reject
# only excessive empty space; the prior rule rejected all readable narration.
_LAYOUT_SPACING = re.compile(r"\n(?:\s*\n){2,}|\n{3,}")


def _style_acceptance_reasons(connector: str, brief: StyleBrief) -> list[str]:
    """Validate only model-added prose against the reviewed role contract."""
    profile = brief.acceptance_profile
    markers = tuple(
        marker for marker in profile.get("required_markers", [])
        if isinstance(marker, str) and marker
    )
    minimum = profile.get("rhythm", {}).get("min_marker_groups", 1)
    matched_groups = sum(marker in connector for marker in markers)
    reasons: list[str] = []
    # Interleaved reviewed components are a stronger, positional style gate
    # than the legacy single-marker heuristic. Keep the marker rule only for
    # old briefs that do not carry the component contract.
    has_component_contract = bool(brief.point_narration_components)
    if (
        not isinstance(minimum, int)
        or minimum < 1
        or (not has_component_contract and matched_groups < minimum)
    ):
        reasons.append("style_marker_missing")
    forbidden = tuple(
        marker for marker in profile.get("forbidden_markers", [])
        if isinstance(marker, str) and marker
    )
    if any(marker in connector for marker in forbidden):
        reasons.append("style_forbidden_marker")
    rhythm = profile.get("rhythm", {})
    sentence_length = rhythm.get("sentence_length")
    default_limit = _SENTENCE_LIMITS.get(sentence_length)
    # A few conversational roles need room for one natural observation turn.
    # This remains a bounded style rule, not a general relaxation: roles must
    # opt in through their reviewed profile and all fact/safety gates still
    # run before publication.
    configured_limit = rhythm.get("max_sentence_characters")
    limit = (
        configured_limit
        if isinstance(configured_limit, int) and 1 <= configured_limit <= 120
        else default_limit
    )
    sentences = [
        re.sub(r"\s+", "", value)
        for value in re.split(r"[。！？!?；;\n]+", connector)
        if re.sub(r"\s+", "", value)
    ]
    if limit is None or any(len(sentence) > limit for sentence in sentences):
        reasons.append("style_rhythm_mismatch")
    contract = profile.get("interaction_contract", {})
    mode = contract.get("mode")
    max_requests = contract.get("max_requests")
    request_count = len(_INTERACTION_REQUEST.findall(connector))
    if (
        not isinstance(max_requests, int)
        or max_requests < 0
        or mode == "none" and request_count
        or request_count > max_requests
    ):
        reasons.append("style_interaction_contract_violation")
    return reasons


def _has_duplicate_connector_sentence(connector: str) -> bool:
    sentences = [
        re.sub(r"\s+", "", value)
        for value in re.split(r"[。！？\n]+", connector)
        if re.sub(r"\s+", "", value)
    ]
    return len(sentences) != len(set(sentences))


def _fact_connector_segments(
    public_text: str,
    plan: NarrationContentPlan,
) -> list[str] | None:
    """Return the prose before, between, and after immutable fact blocks."""
    cursor = 0
    segments: list[str] = []
    found = 0
    for fact in plan.facts:
        position = public_text.find(fact.statement, cursor)
        if position < 0:
            if fact.required:
                return None
            continue
        segments.append(public_text[cursor:position])
        cursor = position + len(fact.statement)
        found += 1
    if not found:
        return None
    segments.append(public_text[cursor:])
    return segments


def _point_style_coverage_reasons(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> list[str]:
    """Require matching reviewed components around every typed fact unit."""
    segments = _fact_connector_segments(candidate.public_text, plan)
    components = brief.point_narration_components
    if segments is None or not components:
        return ["style_coverage_incomplete"]
    opening = tuple(components.get("opening", ()))
    closing = tuple(components.get("closing", ()))
    if not opening or not closing:
        return ["style_coverage_incomplete"]
    if not any(value in segments[0] for value in opening):
        return ["style_coverage_incomplete"]
    if not any(value in segments[-1] for value in closing):
        return ["style_coverage_incomplete"]
    reasons: list[str] = []
    all_typed = {
        topic: tuple(
            value for kind in ("intro", "observation", "transition")
            for value in components.get(f"{topic}_{kind}", ())
        )
        for topic in ("space", "craft", "ornament")
    }
    matched_components: list[str] = []
    for index, fact in enumerate(plan.facts):
        segment = segments[index]
        topic = fact.topic_kind
        is_start = index == 0 or plan.facts[index - 1].unit_id != fact.unit_id
        expected_key = f"{topic}_{'intro' if is_start else 'observation'}"
        expected = tuple(components.get(expected_key, ()))
        if not expected or not any(value in segment for value in expected):
            reasons.append(f"{topic}_style_coverage_incomplete")
        if is_start and index > 0:
            previous_topic = plan.facts[index - 1].topic_kind
            transition = tuple(components.get(f"{previous_topic}_transition", ()))
            if not transition or not any(value in segment for value in transition):
                reasons.append(f"{previous_topic}_style_coverage_incomplete")
        for other_topic in all_typed:
            wrong_values = tuple(
                value for kind in ("intro", "observation")
                for value in components.get(f"{other_topic}_{kind}", ())
            )
            if other_topic != topic and any(value in segment for value in wrong_values):
                reasons.append("style_component_topic_mismatch")
        for values in components.values():
            for value in values:
                if value and value in segment:
                    matched_components.append(value)
    if any(
        left == right for left, right in zip(matched_components, matched_components[1:])
    ):
        reasons.append("repeated_style_component")
    if reasons:
        reasons.append("style_coverage_incomplete")
    return list(dict.fromkeys(reasons))


def _compact_point_style_coverage_reasons(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> list[str]:
    segments = _fact_connector_segments(candidate.public_text, plan)
    components = brief.point_narration_components
    if segments is None:
        return ["style_coverage_incomplete"]
    compact_components = bool(components.get("compact_opening"))
    opening_key = "compact_opening" if compact_components else "opening"
    closing_key = "compact_closing" if compact_components else "closing"
    if not any(value in segments[0] for value in components.get(opening_key, ())):
        return ["style_coverage_incomplete"]
    if not any(value in segments[-1] for value in components.get(closing_key, ())):
        return ["style_coverage_incomplete"]
    unit_count = sum(
        index == 0 or plan.facts[index - 1].unit_id != fact.unit_id
        for index, fact in enumerate(plan.facts)
    )
    for index, fact in enumerate(plan.facts):
        is_start = index == 0 or plan.facts[index - 1].unit_id != fact.unit_id
        if not compact_components and is_start and not any(
            value in segments[index]
            for value in components.get(f"{fact.topic_kind}_intro", ())
        ):
            return ["style_coverage_incomplete"]
        is_unit_end = index == len(plan.facts) - 1 or plan.facts[index + 1].unit_id != fact.unit_id
        if compact_components and is_unit_end and not any(
            value in segments[index + 1]
            for value in components.get(f"{fact.topic_kind}_micro_observation", ())
        ):
            return [f"{fact.topic_kind}_compact_middle_coverage_incomplete", "style_coverage_incomplete"]
    if compact_components and unit_count > 1 and not any(
        value in "".join(segments)
        for topic in ("space", "craft", "ornament")
        for value in components.get(f"{topic}_micro_transition", ())
    ):
        return ["compact_transition_incomplete", "style_coverage_incomplete"]
    return []


@dataclass(frozen=True)
class NarrationValidationResult:
    validation_status: str
    reason_codes: tuple[str, ...]
    state_writes: tuple[()] = ()
    same_fact_boundary: bool = False
    role_consistent: bool = False
    within_budget: bool = False
    public_message_safe: bool = False
    layout_passed: bool = False
    layout_reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_status": self.validation_status,
            "reason_codes": list(self.reason_codes),
            "state_writes": [],
            "same_fact_boundary": self.same_fact_boundary,
            "role_consistent": self.role_consistent,
            "within_budget": self.within_budget,
            "public_message_safe": self.public_message_safe,
            "layout_passed": self.layout_passed,
            "layout_reason_codes": list(self.layout_reason_codes),
        }


def _validate_role_narration_contract(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
    *,
    require_point_style_coverage: bool,
    compact: bool = False,
    preserve_fact_layout: bool = False,
) -> NarrationValidationResult:
    reasons: list[str] = []
    allowed_ids = {fact.fact_id for fact in plan.facts}
    required_ids = {fact.fact_id for fact in plan.facts if fact.required}
    used_ids = set(candidate.used_fact_ids)
    if candidate.generation_status != "generated":
        reasons.append(candidate.reason_code or "generation_failed")
    if candidate.style_id != plan.style_id or brief.style_id != plan.style_id:
        reasons.append("style_mismatch")
    if not used_ids.issubset(allowed_ids) or not required_ids.issubset(used_ids):
        reasons.append("fact_id_boundary_violation")
    expected_statement_counts = Counter(
        fact.statement for fact in plan.facts if fact.fact_id in used_ids
    )
    actual_statement_counts = {
        statement: candidate.public_text.count(statement)
        for statement in expected_statement_counts
    }
    if any(actual_statement_counts[value] != count for value, count in expected_statement_counts.items()):
        reasons.append("approved_statement_not_preserved")
    connector_segments = _fact_connector_segments(candidate.public_text, plan)
    if connector_segments is None:
        reasons.append("approved_statement_order_changed")
    connector = role_connector_text(candidate.public_text, plan)
    # Paragraph separators are presentation-only. Generation budgets connector
    # prose after whitespace normalization, so validation must use the same
    # measure rather than charging a semantic blank line as content.
    if len(re.sub(r"\s+", "", connector)) > role_connector_character_limit(plan):
        reasons.append("unbounded_role_connectors")
    # Triggers already present in an approved statement are harmless. Only
    # inspect model-added connective prose for new factual assertions.
    if UNAPPROVED_CONNECTOR_FACT_TRIGGER.search(connector):
        reasons.append("unapproved_fact_trigger")
    if _INTERNAL.search(candidate.public_text):
        reasons.append("internal_field_leak")
    if _DANGEROUS.search(candidate.public_text):
        reasons.append("unsafe_or_coercive_expression")
    malformed_punctuation = bool(_MALFORMED_PUNCTUATION.search(candidate.public_text))
    if malformed_punctuation:
        reasons.append("malformed_punctuation")
    layout_reasons: list[str] = []
    if malformed_punctuation:
        layout_reasons.append("malformed_punctuation")
    # Stop guidance owns the complete visitor layout.  A controlled blank line
    # is now a semantic paragraph boundary, not a validation failure. QA wraps
    # an already-published answer and still audits only model-added prose.
    layout_segments = (
        connector_segments
        if preserve_fact_layout and connector_segments is not None
        else [candidate.public_text]
    )
    layout_text = "".join(layout_segments)
    if any(_LAYOUT_HEADING.search(segment) for segment in layout_segments):
        layout_reasons.append("layout_heading_leak")
    if any(_LAYOUT_MARKDOWN.search(segment) for segment in layout_segments):
        layout_reasons.append("layout_markdown_leak")
    if any(_LAYOUT_SPACING.search(segment) for segment in layout_segments):
        layout_reasons.append("layout_spacing_invalid")
    if not candidate.public_text.strip().endswith(("。", "！", "？")):
        layout_reasons.append("layout_terminal_punctuation_missing")
    reasons.extend(layout_reasons)
    if _has_duplicate_connector_sentence(connector):
        reasons.append("repeated_role_expression")
    # Typed component coverage belongs to the stop-guidance contract.  QA
    # plans deliberately wrap one already-approved answer as ``qa:*`` and do
    # not contain space/craft/ornament fact units.  Applying the point gate to
    # them makes every otherwise-safe QA Shadow candidate fail with
    # ``style_coverage_incomplete``.
    if require_point_style_coverage and candidate.reason_code != "natural_discourse_generated":
        coverage_validator = (
            _compact_point_style_coverage_reasons
            if compact else _point_style_coverage_reasons
        )
        reasons.extend(coverage_validator(candidate, plan, brief))
    if any(pattern and pattern in candidate.public_text for pattern in brief.prohibited_patterns):
        reasons.append("style_prohibited_pattern")
    reasons.extend(_style_acceptance_reasons(connector, brief))
    if not plan.interaction_allowed and (
        "?" in candidate.public_text
        or "？" in candidate.public_text
        or re.search(r"(?:请你|试着|任务|回答|拍照|跟着做)", candidate.public_text)
    ):
        reasons.append("listen_only_interaction_violation")
    # Generation has already proved the reviewed fact allocation fits the
    # stop budget.  Validate the identical connector cap here; estimating
    # seconds again would create a second, stricter budget and reject a
    # scaffold that generation has just accepted.
    connector_length = len(re.sub(r"\s+", "", connector))
    within_budget = (
        candidate.generation_status == "generated"
        and plan.budget_seconds > 0
        and connector_length <= role_connector_character_limit(plan)
    )
    if not within_budget:
        reasons.append("content_budget_exceeded")
    safe_boundary = public_visitor_message_or_fallback(candidate.public_text) == candidate.public_text
    if not safe_boundary or not candidate.public_text:
        reasons.append("public_message_boundary_rejected")
    same_fact_boundary = not any(
        reason in reasons for reason in (
            "fact_id_boundary_violation", "approved_statement_not_preserved",
            "approved_statement_order_changed", "unapproved_fact_trigger",
        )
    )
    role_consistent = not any(
        reason in reasons for reason in (
            "style_mismatch", "style_prohibited_pattern",
            "style_marker_missing", "style_forbidden_marker",
            "style_rhythm_mismatch", "style_interaction_contract_violation",
            "listen_only_interaction_violation", "unbounded_role_connectors",
            "malformed_punctuation", "repeated_role_expression",
            "style_coverage_incomplete",
            "space_style_coverage_incomplete", "craft_style_coverage_incomplete",
            "ornament_style_coverage_incomplete", "style_component_topic_mismatch",
            "repeated_style_component",
        )
    )
    return NarrationValidationResult(
        validation_status="accepted" if not reasons else "rejected",
        reason_codes=tuple(dict.fromkeys(reasons)),
        same_fact_boundary=same_fact_boundary,
        role_consistent=role_consistent,
        within_budget=within_budget,
        public_message_safe=safe_boundary and not bool(_INTERNAL.search(candidate.public_text)),
        layout_passed=not layout_reasons,
        layout_reason_codes=tuple(dict.fromkeys(layout_reasons)),
    )


def validate_stop_guidance_role_narration(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
    *,
    compact: bool = False,
) -> NarrationValidationResult:
    """Validate point narration, including typed component coverage."""
    if plan.stop_id.startswith("qa:"):
        return NarrationValidationResult(
            validation_status="rejected",
            reason_codes=("stop_guidance_plan_required",),
        )
    return _validate_role_narration_contract(
        candidate, plan, brief, require_point_style_coverage=True, compact=compact,
    )


def validate_qa_role_narration(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> NarrationValidationResult:
    """Validate QA narration without applying point-component requirements."""
    if not plan.stop_id.startswith("qa:"):
        return NarrationValidationResult(
            validation_status="rejected",
            reason_codes=("qa_plan_required",),
        )
    return _validate_role_narration_contract(
        candidate,
        plan,
        brief,
        require_point_style_coverage=False,
        preserve_fact_layout=True,
    )


def validate_role_narration(
    candidate: RoleNarrationCandidate,
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> NarrationValidationResult:
    """Compatibility dispatcher for historical callers and frozen tests."""
    validator = (
        validate_qa_role_narration
        if plan.stop_id.startswith("qa:")
        else validate_stop_guidance_role_narration
    )
    return validator(candidate, plan, brief)
