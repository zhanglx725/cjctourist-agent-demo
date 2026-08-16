"""Deterministic preflight planning for bounded, multi-turn narration."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Iterable, Mapping

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import StyleBrief


class NarrationBudgetMode(StrEnum):
    FULL = "full"
    COMPACT = "compact"
    SPLIT = "split"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class NarrationBudgetDecision:
    mode: NarrationBudgetMode
    budget_seconds: int
    fact_seconds: int
    connector_seconds: int
    selected_fact_ids: tuple[str, ...]
    deferred_fact_ids: tuple[str, ...]
    reason_code: str
    schema_version: str = "narration_budget_decision_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "budget_seconds": self.budget_seconds,
            "fact_seconds": self.fact_seconds,
            "connector_seconds": self.connector_seconds,
            "selected_fact_ids": list(self.selected_fact_ids),
            "deferred_fact_ids": list(self.deferred_fact_ids),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class NarrationContinuation:
    stop_id: str
    style_id: str
    remaining_facts: tuple[NarrationFact, ...]
    published_fact_ids: tuple[str, ...]
    freshness_token: str
    language: str = "zh"
    budget_seconds: int = 0
    interaction_allowed: bool = True
    status: str = "ready"
    schema_version: str = "narration_continuation_v1"

    @property
    def remaining_fact_ids(self) -> tuple[str, ...]:
        return tuple(fact.fact_id for fact in self.remaining_facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "stop_id": self.stop_id,
            "style_id": self.style_id,
            "remaining_fact_ids": list(self.remaining_fact_ids),
            "remaining_facts": [fact.to_dict() for fact in self.remaining_facts],
            "published_fact_ids": list(self.published_fact_ids),
            "freshness_token": self.freshness_token,
            "language": self.language,
            "budget_seconds": self.budget_seconds,
            "interaction_allowed": self.interaction_allowed,
        }

    def is_fresh(self, *, stop_id: str, style_id: str, freshness_token: str) -> bool:
        return bool(
            self.status == "ready"
            and self.stop_id == stop_id
            and self.style_id == style_id
            and self.freshness_token == freshness_token
            and self.remaining_fact_ids
        )


def _visible(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def _fact_seconds(plan: NarrationContentPlan, facts: Iterable[NarrationFact]) -> int:
    selected = tuple(facts)
    all_chars = sum(_visible(fact.statement) for fact in plan.facts)
    selected_chars = sum(_visible(fact.statement) for fact in selected)
    if not selected_chars:
        return 0
    total_seconds = plan.allocated_content_seconds or math.ceil(all_chars / 4)
    return max(1, math.ceil(total_seconds * selected_chars / max(1, all_chars)))


def _component_chars(brief: StyleBrief, facts: tuple[NarrationFact, ...], *, compact: bool) -> int:
    """Count the exact deterministic scaffold selected by the renderer.

    Budget preflight must use the same component index, transition placement,
    duplicate suppression, and compact/full rules as
    ``apply_point_narration_scaffold``.  The former implementation used the
    shortest value in each component family and did not count transitions
    between fact units.  A plan could therefore pass preflight and then fail
    after the model call with ``style_scaffold_budget_exceeded``.
    """
    components = brief.point_narration_components

    def selected(kind: str, index: int, *, previous: str = "") -> str:
        values = components.get(kind, ())
        if not values:
            return ""
        normalized = tuple(str(value).strip() for value in values if str(value).strip())
        if not normalized:
            return ""
        for offset in range(len(normalized)):
            value = normalized[(index + offset) % len(normalized)]
            if value != previous:
                return value
        return normalized[index % len(normalized)]

    selected_components: list[str] = []
    compact_components = bool(components.get("compact_opening"))
    opening_key = "compact_opening" if compact and compact_components else "opening"
    closing_key = "compact_closing" if compact and compact_components else "closing"
    opening = selected(opening_key, 0)
    if opening:
        selected_components.append(opening)
    previous_component = opening
    compact_transition_emitted = False
    for index, fact in enumerate(facts):
        is_unit_start = index == 0 or facts[index - 1].unit_id != fact.unit_id
        if is_unit_start and not (compact and compact_components):
            intro = selected(
                f"{fact.topic_kind}_intro", index,
                previous=previous_component,
            )
            if intro and intro != previous_component:
                selected_components.append(intro)
                previous_component = intro
        if compact and compact_components:
            is_unit_end = index == len(facts) - 1 or facts[index + 1].unit_id != fact.unit_id
            if is_unit_end:
                observation = selected(
                    f"{fact.topic_kind}_micro_observation", index,
                    previous=previous_component,
                )
                if observation and observation != previous_component:
                    selected_components.append(observation)
                    previous_component = observation
            if is_unit_end and index < len(facts) - 1 and not compact_transition_emitted:
                transition = selected(
                    f"{fact.topic_kind}_micro_transition", index,
                    previous=previous_component,
                )
                if transition and transition != previous_component:
                    selected_components.append(transition)
                    previous_component = transition
                    compact_transition_emitted = True
        elif not compact and index < len(facts) - 1:
            next_fact = facts[index + 1]
            kind = "observation" if next_fact.unit_id == fact.unit_id else "transition"
            bridge = selected(
                f"{fact.topic_kind}_{kind}", index,
                previous=previous_component,
            )
            if bridge and bridge != previous_component:
                selected_components.append(bridge)
                previous_component = bridge
    if not compact:
        appreciation = selected(
            "appreciation", len(facts), previous=previous_component,
        )
        if appreciation and appreciation != previous_component:
            selected_components.append(appreciation)
            previous_component = appreciation
    closing = selected(closing_key, len(facts), previous=previous_component)
    if closing and closing != previous_component:
        selected_components.append(closing)
    return sum(_visible(value) for value in selected_components)


def _connector_seconds(brief: StyleBrief, facts: tuple[NarrationFact, ...], *, compact: bool) -> int:
    return math.ceil(_component_chars(brief, facts, compact=compact) / 4)


def decide_narration_budget(
    plan: NarrationContentPlan,
    brief: StyleBrief,
) -> NarrationBudgetDecision:
    """Choose full, compact, one-unit split, or deterministic fallback."""
    all_facts = tuple(plan.facts)
    all_ids = tuple(fact.fact_id for fact in all_facts)
    if plan.status != "ready" or plan.budget_seconds <= 0 or not all_facts:
        return NarrationBudgetDecision(
            NarrationBudgetMode.FALLBACK, max(0, plan.budget_seconds), 0, 0,
            (), all_ids, "plan_not_feasible",
        )
    facts_seconds = _fact_seconds(plan, all_facts)
    full_connector = _connector_seconds(brief, all_facts, compact=False)
    if facts_seconds + full_connector <= plan.budget_seconds:
        return NarrationBudgetDecision(
            NarrationBudgetMode.FULL, plan.budget_seconds, facts_seconds,
            full_connector, all_ids, (), "full_scaffold_fits",
        )
    compact_connector = _connector_seconds(brief, all_facts, compact=True)
    if facts_seconds + compact_connector <= plan.budget_seconds:
        return NarrationBudgetDecision(
            NarrationBudgetMode.COMPACT, plan.budget_seconds, facts_seconds,
            compact_connector, all_ids, (), "compact_scaffold_fits",
        )
    first_unit = all_facts[0].unit_id
    selected = tuple(fact for fact in all_facts if fact.unit_id == first_unit)
    split_fact_seconds = _fact_seconds(plan, selected)
    split_connector = _connector_seconds(brief, selected, compact=True)
    selected_ids = tuple(fact.fact_id for fact in selected)
    deferred_ids = tuple(fact.fact_id for fact in all_facts if fact.fact_id not in selected_ids)
    if deferred_ids and split_fact_seconds + split_connector <= plan.budget_seconds:
        return NarrationBudgetDecision(
            NarrationBudgetMode.SPLIT, plan.budget_seconds, split_fact_seconds,
            split_connector, selected_ids, deferred_ids, "first_fact_unit_fits",
        )
    return NarrationBudgetDecision(
        NarrationBudgetMode.FALLBACK, plan.budget_seconds, facts_seconds,
        compact_connector, (), all_ids, "minimum_fact_unit_exceeds_budget",
    )


def continuation_from_decision(
    plan: NarrationContentPlan,
    decision: NarrationBudgetDecision,
    *,
    freshness_token: str,
) -> NarrationContinuation | None:
    if decision.mode is not NarrationBudgetMode.SPLIT or not decision.deferred_fact_ids:
        return None
    return NarrationContinuation(
        stop_id=plan.stop_id, style_id=plan.style_id,
        remaining_facts=tuple(
            fact for fact in plan.facts
            if fact.fact_id in set(decision.deferred_fact_ids)
        ),
        published_fact_ids=decision.selected_fact_ids,
        freshness_token=freshness_token,
        language=plan.language,
        budget_seconds=plan.budget_seconds,
        interaction_allowed=plan.interaction_allowed,
    )


def plan_for_budget_decision(
    plan: NarrationContentPlan,
    decision: NarrationBudgetDecision,
) -> NarrationContentPlan | None:
    """Return the exact fact boundary authorized for this visitor turn."""
    if decision.mode is NarrationBudgetMode.FALLBACK:
        return None
    selected = set(decision.selected_fact_ids)
    facts = tuple(fact for fact in plan.facts if fact.fact_id in selected)
    if not facts or tuple(fact.fact_id for fact in facts) != decision.selected_fact_ids:
        return None
    return replace(
        plan, facts=facts,
        allocated_content_seconds=decision.fact_seconds,
        scaffold_mode=(
            "compact" if decision.mode in {
                NarrationBudgetMode.COMPACT, NarrationBudgetMode.SPLIT,
            } else "full"
        ),
    )


def narration_continuation_from_dict(
    value: Mapping[str, Any] | None,
) -> NarrationContinuation | None:
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != "narration_continuation_v1"
        or value.get("status") not in {"ready", "completed", "cancelled"}
        or not isinstance(value.get("remaining_facts"), list)
        or not isinstance(value.get("published_fact_ids"), list)
    ):
        return None
    try:
        facts = tuple(
            NarrationFact(
                fact_id=str(item["fact_id"]),
                semantic_role=str(item["semantic_role"]),
                statement=str(item["statement"]),
                required=bool(item.get("required", True)),
            )
            for item in value["remaining_facts"]
        )
        continuation = NarrationContinuation(
            stop_id=str(value.get("stop_id") or ""),
            style_id=str(value.get("style_id") or ""),
            remaining_facts=facts,
            published_fact_ids=tuple(str(item) for item in value["published_fact_ids"]),
            freshness_token=str(value.get("freshness_token") or ""),
            language=str(value.get("language") or "zh"),
            budget_seconds=int(value.get("budget_seconds") or 0),
            interaction_allowed=bool(value.get("interaction_allowed")),
            status=str(value["status"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if (
        not continuation.stop_id or not continuation.style_id
        or not continuation.freshness_token
        or len(set(continuation.remaining_fact_ids)) != len(continuation.remaining_fact_ids)
        or set(continuation.remaining_fact_ids) & set(continuation.published_fact_ids)
    ):
        return None
    return continuation


def classify_continuation_action(text: str) -> str | None:
    normalized = re.sub(r"[\s，。！？、,.!?]", "", str(text or "")).lower()
    if normalized in {"继续", "下一部分", "继续讲", "接着讲", "然后呢"}:
        return "continue"
    if normalized in {"先讲工艺", "讲工艺", "先说工艺"}:
        return "craft"
    if normalized in {"跳过剩余内容", "跳过剩余", "不用继续", "不讲了"}:
        return "skip"
    return None


def resume_plan_from_continuation(
    continuation: NarrationContinuation,
    *,
    action: str,
) -> NarrationContentPlan | None:
    if continuation.status != "ready" or action == "skip":
        return None
    facts = continuation.remaining_facts
    if action == "craft":
        facts = tuple(fact for fact in facts if fact.topic_kind == "craft")
    if action not in {"continue", "craft"} or not facts:
        return None
    return NarrationContentPlan(
        stop_id=continuation.stop_id, style_id=continuation.style_id,
        language=continuation.language, budget_seconds=continuation.budget_seconds,
        facts=facts, must_include=("approved_observation_detail",),
        already_covered=continuation.published_fact_ids, must_not_claim=(),
        interaction_allowed=continuation.interaction_allowed,
        requested_scope="craft" if action == "craft" else "whole_stop",
    )


def advance_continuation(
    continuation: NarrationContinuation,
    published_fact_ids: Iterable[str],
) -> NarrationContinuation:
    published = tuple(dict.fromkeys(str(item) for item in published_fact_ids))
    allowed = set(continuation.remaining_fact_ids)
    if not published or not set(published).issubset(allowed):
        return continuation
    remaining = tuple(
        fact for fact in continuation.remaining_facts if fact.fact_id not in set(published)
    )
    history = tuple(dict.fromkeys((*continuation.published_fact_ids, *published)))
    return NarrationContinuation(
        stop_id=continuation.stop_id, style_id=continuation.style_id,
        remaining_facts=remaining, published_fact_ids=history,
        freshness_token=continuation.freshness_token,
        language=continuation.language, budget_seconds=continuation.budget_seconds,
        interaction_allowed=continuation.interaction_allowed,
        status="ready" if remaining else "completed",
    )
