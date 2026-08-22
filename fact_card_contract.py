"""Versioned contract for visitor-facing, reviewed fact cards.

This is the migration boundary for high-frequency service QA.  A card holds
only public factual prose and its rendering policy; provenance stays in
``source_refs`` for audit and must never be copied into a visitor answer.
The contract is deliberately read-only: it has no dependency on AgentState,
TourState, VisitorProfile, retrieval, or a language model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping


FACT_CARD_SCHEMA_VERSION = "visitor_fact_card_v1"
FACT_CARD_DOMAINS = frozenset({
    "opening_hours",
    "transport",
    "ticketing",
    "visit_service",
    "nearby_recommendation",
})
FACT_CARD_QUESTION_TYPES = frozenset({
    "time",
    "availability",
    "method",
    "rule",
    "eligibility",
    "location",
    "recommendation",
})
FACT_CARD_TEMPLATE_IDS = frozenset({
    "time_window",
    "transport_options",
    "service_rule",
    "service_steps",
    "ticketing_rule",
    "ticketing_method",
    "nearby_candidates",
})
FRESHNESS_POLICIES = frozenset({"static", "dynamic"})
PARTIAL_ANSWER_POLICIES = frozenset({"answer_confirmed_portion", "clarify"})
RUNTIME_STATUSES = frozenset({"enabled", "disabled"})

_CARD_ID = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
_SOURCE_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,119}$")
_PUBLIC_FACT_FORBIDDEN = (
    ".md", "source_ids", "chunk_id", "title_path", "node_id", "http://",
)
_PUBLIC_URL = re.compile(r"https://[^\s，。；！？]+")
_ALLOWED_PUBLIC_FACT_URLS = frozenset({"https://wx.gzcjc.com.cn"})


class FactCardValidationError(ValueError):
    """Raised when a card cannot safely participate in the shared renderer."""


def _string_tuple(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise FactCardValidationError(f"{field} must be a list of strings")
    items = tuple(str(item).strip() for item in value)
    if any(not item for item in items):
        raise FactCardValidationError(f"{field} contains an empty value")
    if not allow_empty and not items:
        raise FactCardValidationError(f"{field} must not be empty")
    if len(set(items)) != len(items):
        raise FactCardValidationError(f"{field} contains duplicates")
    return items


@dataclass(frozen=True)
class FactCard:
    """One reviewed fact bundle rendered by a fixed visitor template.

    ``fact_statements`` are the only factual sentences a future renderer may
    expose. ``applicability_conditions`` constrain when they are applicable.
    ``partial_answer_policy`` tells the renderer what to do if a composite
    question has only this card available; it must never invent the missing
    portion or fail the entire answer by default.
    """

    card_id: str
    domain: str
    question_types: tuple[str, ...]
    trigger_phrases: tuple[str, ...]
    fact_statements: tuple[str, ...]
    applicability_conditions: tuple[str, ...]
    freshness_policy: str
    freshness_notice: str | None
    public_template_id: str
    partial_answer_policy: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    runtime_status: str = "enabled"
    schema_version: str = FACT_CARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FACT_CARD_SCHEMA_VERSION:
            raise FactCardValidationError("unsupported fact-card schema version")
        if not isinstance(self.card_id, str) or not _CARD_ID.fullmatch(self.card_id):
            raise FactCardValidationError("card_id must be a stable snake_case identifier")
        if self.domain not in FACT_CARD_DOMAINS:
            raise FactCardValidationError("unknown fact-card domain")
        question_types = _string_tuple(self.question_types, "question_types")
        object.__setattr__(self, "question_types", question_types)
        if not set(question_types).issubset(FACT_CARD_QUESTION_TYPES):
            raise FactCardValidationError("unknown fact-card question type")
        trigger_phrases = _string_tuple(self.trigger_phrases, "trigger_phrases")
        object.__setattr__(self, "trigger_phrases", trigger_phrases)
        statements = _string_tuple(self.fact_statements, "fact_statements")
        object.__setattr__(self, "fact_statements", statements)
        for statement in statements:
            if len(statement) > 600:
                raise FactCardValidationError("fact statement is too long")
            lowered = statement.casefold()
            if any(token in lowered for token in _PUBLIC_FACT_FORBIDDEN):
                raise FactCardValidationError("fact statement contains non-public retrieval text")
            if any(url not in _ALLOWED_PUBLIC_FACT_URLS for url in _PUBLIC_URL.findall(statement)):
                raise FactCardValidationError("fact statement contains an unapproved public URL")
        conditions = _string_tuple(self.applicability_conditions, "applicability_conditions", allow_empty=True)
        limitations = _string_tuple(self.limitations, "limitations", allow_empty=True)
        object.__setattr__(self, "applicability_conditions", conditions)
        object.__setattr__(self, "limitations", limitations)
        refs = _string_tuple(self.source_refs, "source_refs")
        object.__setattr__(self, "source_refs", refs)
        if any(not _SOURCE_REF.fullmatch(ref) for ref in refs):
            raise FactCardValidationError("source_refs contains an invalid audit reference")
        if self.freshness_policy not in FRESHNESS_POLICIES:
            raise FactCardValidationError("unknown freshness policy")
        notice = str(self.freshness_notice or "").strip()
        if self.freshness_policy == "dynamic" and not notice:
            raise FactCardValidationError("dynamic cards require a freshness notice")
        if self.freshness_policy == "static" and self.freshness_notice not in (None, ""):
            raise FactCardValidationError("static cards must not carry a freshness notice")
        object.__setattr__(self, "freshness_notice", notice or None)
        if self.public_template_id not in FACT_CARD_TEMPLATE_IDS:
            raise FactCardValidationError("unknown public template")
        if self.partial_answer_policy not in PARTIAL_ANSWER_POLICIES:
            raise FactCardValidationError("unknown partial-answer policy")
        if self.runtime_status not in RUNTIME_STATUSES:
            raise FactCardValidationError("unknown fact-card runtime status")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "question_types", "trigger_phrases", "fact_statements",
            "applicability_conditions", "source_refs", "limitations",
        ):
            result[key] = list(result[key])
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "FactCard | None":
        required = {
            "schema_version", "card_id", "domain", "question_types", "trigger_phrases",
            "fact_statements", "applicability_conditions", "freshness_policy",
            "freshness_notice", "public_template_id", "partial_answer_policy",
            "source_refs", "limitations", "runtime_status",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            return None
        try:
            return cls(
                schema_version=value["schema_version"],
                card_id=value["card_id"],
                domain=value["domain"],
                question_types=tuple(value["question_types"]),
                trigger_phrases=tuple(value["trigger_phrases"]),
                fact_statements=tuple(value["fact_statements"]),
                applicability_conditions=tuple(value["applicability_conditions"]),
                freshness_policy=value["freshness_policy"],
                freshness_notice=value["freshness_notice"],
                public_template_id=value["public_template_id"],
                partial_answer_policy=value["partial_answer_policy"],
                source_refs=tuple(value["source_refs"]),
                limitations=tuple(value["limitations"]),
                runtime_status=value["runtime_status"],
            )
        except (FactCardValidationError, TypeError, KeyError):
            return None


@dataclass(frozen=True)
class FactCardCatalog:
    """One versioned, fail-closed collection of independently usable cards."""

    cards: tuple[FactCard, ...]
    schema_version: str = FACT_CARD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FACT_CARD_SCHEMA_VERSION:
            raise FactCardValidationError("unsupported fact-card catalog version")
        if not self.cards:
            raise FactCardValidationError("fact-card catalog must not be empty")
        if any(not isinstance(card, FactCard) for card in self.cards):
            raise FactCardValidationError("catalog contains a non-fact-card item")
        card_ids = tuple(card.card_id for card in self.cards)
        if len(set(card_ids)) != len(card_ids):
            raise FactCardValidationError("catalog contains duplicate card_id values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cards": [card.to_dict() for card in self.cards],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "FactCardCatalog | None":
        if not isinstance(value, Mapping) or set(value) != {"schema_version", "cards"}:
            return None
        raw_cards = value.get("cards")
        if not isinstance(raw_cards, list):
            return None
        cards = tuple(FactCard.from_dict(raw) for raw in raw_cards)
        if any(card is None for card in cards):
            return None
        try:
            return cls(cards=tuple(card for card in cards if card is not None), schema_version=value["schema_version"])
        except (FactCardValidationError, TypeError, KeyError):
            return None


__all__ = [
    "FACT_CARD_DOMAINS",
    "FACT_CARD_QUESTION_TYPES",
    "FACT_CARD_SCHEMA_VERSION",
    "FACT_CARD_TEMPLATE_IDS",
    "FactCard",
    "FactCardCatalog",
    "FactCardValidationError",
]
