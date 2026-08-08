"""Immutable, thread-local coverage records for E5 narration.

NarrationCoverage answers only one question: which crafts and reviewed
ornaments have already received a successful, evidence-backed introduction in
the current tour session?  It deliberately stores no RAG text and does not
depend on TourState, VisitorProfile, StopProgram, or LangGraph.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "v1"
VALID_SUBJECT_KINDS = frozenset({"craft", "ornament"})
VALID_INTRODUCED_BY = frozenset(
    {
        "stop_guidance",
        "tour_qa",
        "narration_commit",
        "deterministic_narration_fallback",
    }
)
GUIDE_CARDS_FILE = Path("data/chen_clan_academy/routes/node_guide_cards_v1.json")


class NarrationCoverageError(ValueError):
    """Raised when a coverage snapshot or atomic introduction is invalid."""


def _clean_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip()):
        raise NarrationCoverageError(f"{field} must be a non-empty string")
    return cleaned


def _normalise_source_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise NarrationCoverageError("source_ids must be a sequence")
    source_ids = tuple(dict.fromkeys(_clean_text(source_id, "source_id") for source_id in value))
    if not source_ids:
        raise NarrationCoverageError("source_ids must not be empty")
    return source_ids


def canonical_craft_ids(cards_file: Path = GUIDE_CARDS_FILE) -> frozenset[str]:
    """Read only the reviewed craft labels used by point-guide cards.

    This is intentionally exact after whitespace cleanup: E5-A1 must not
    merge aliases or invent a new craft identifier while recording coverage.
    """
    try:
        payload = json.loads(cards_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NarrationCoverageError("reviewed guide cards are unavailable") from exc
    cards = payload.get("cards", []) if isinstance(payload, dict) else []
    values = {
        craft.strip()
        for card in cards
        if isinstance(card, dict)
        for ornament in card.get("ornaments", [])
        if isinstance(ornament, dict)
        for craft in [ornament.get("craft")]
        if isinstance(craft, str) and craft.strip()
    }
    if not values:
        raise NarrationCoverageError("reviewed guide cards contain no craft identifiers")
    return frozenset(values)


@dataclass(frozen=True)
class IntroductionRecord:
    subject_kind: str
    subject_id: str
    source_ids: tuple[str, ...]
    introduced_by: str
    node_id: str
    turn_id: str

    def __post_init__(self) -> None:
        kind = _clean_text(self.subject_kind, "subject_kind")
        if kind not in VALID_SUBJECT_KINDS:
            raise NarrationCoverageError("subject_kind is invalid")
        subject_id = _clean_text(self.subject_id, "subject_id")
        introduced_by = _clean_text(self.introduced_by, "introduced_by")
        if introduced_by not in VALID_INTRODUCED_BY:
            raise NarrationCoverageError("introduced_by is invalid")
        node_id = _clean_text(self.node_id, "node_id")
        turn_id = _clean_text(self.turn_id, "turn_id")
        source_ids = _normalise_source_ids(self.source_ids)
        if kind == "craft" and subject_id not in canonical_craft_ids():
            raise NarrationCoverageError("craft subject_id is not a reviewed canonical craft")
        object.__setattr__(self, "subject_kind", kind)
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "introduced_by", introduced_by)
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(self, "turn_id", turn_id)
        object.__setattr__(self, "source_ids", source_ids)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "IntroductionRecord":
        if not isinstance(value, dict):
            raise NarrationCoverageError("introduction record must be a mapping")
        expected = {"subject_kind", "subject_id", "source_ids", "introduced_by", "node_id", "turn_id"}
        if set(value) != expected:
            raise NarrationCoverageError("introduction record fields are incomplete or unexpected")
        return cls(
            subject_kind=value["subject_kind"],
            subject_id=value["subject_id"],
            source_ids=value["source_ids"],
            introduced_by=value["introduced_by"],
            node_id=value["node_id"],
            turn_id=value["turn_id"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "source_ids": list(self.source_ids),
            "introduced_by": self.introduced_by,
            "node_id": self.node_id,
            "turn_id": self.turn_id,
        }


@dataclass(frozen=True)
class NarrationCoverage:
    schema_version: str
    introduced_craft_ids: tuple[str, ...]
    introduced_ornament_ids: tuple[str, ...]
    introduction_records: tuple[IntroductionRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise NarrationCoverageError("unsupported narration coverage schema")
        records = tuple(self.introduction_records)
        if not all(isinstance(record, IntroductionRecord) for record in records):
            raise NarrationCoverageError("introduction_records are invalid")
        craft_ids = tuple(record.subject_id for record in records if record.subject_kind == "craft")
        ornament_ids = tuple(record.subject_id for record in records if record.subject_kind == "ornament")
        if len(craft_ids) != len(set(craft_ids)) or len(ornament_ids) != len(set(ornament_ids)):
            raise NarrationCoverageError("first introductions must be unique per subject")
        if tuple(self.introduced_craft_ids) != craft_ids:
            raise NarrationCoverageError("introduced_craft_ids must be derived from records")
        if tuple(self.introduced_ornament_ids) != ornament_ids:
            raise NarrationCoverageError("introduced_ornament_ids must be derived from records")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "introduced_craft_ids": list(self.introduced_craft_ids),
            "introduced_ornament_ids": list(self.introduced_ornament_ids),
            "introduction_records": [record.to_dict() for record in self.introduction_records],
        }


def empty_narration_coverage() -> NarrationCoverage:
    return NarrationCoverage(SCHEMA_VERSION, (), (), ())


def load_narration_coverage(value: NarrationCoverage | dict[str, Any] | None) -> NarrationCoverage:
    """Load a validated snapshot; a missing legacy AgentState field is empty."""
    if value is None:
        return empty_narration_coverage()
    if isinstance(value, NarrationCoverage):
        return value
    if not isinstance(value, dict):
        raise NarrationCoverageError("narration_coverage must be a mapping or None")
    expected = {"schema_version", "introduced_craft_ids", "introduced_ornament_ids", "introduction_records"}
    if set(value) != expected:
        raise NarrationCoverageError("narration_coverage fields are incomplete or unexpected")
    records = tuple(IntroductionRecord.from_dict(record) for record in value["introduction_records"])
    return NarrationCoverage(
        schema_version=value["schema_version"],
        introduced_craft_ids=tuple(value["introduced_craft_ids"]),
        introduced_ornament_ids=tuple(value["introduced_ornament_ids"]),
        introduction_records=records,
    )


def commit_introductions(
    coverage: NarrationCoverage | dict[str, Any] | None,
    records: Iterable[IntroductionRecord | dict[str, Any]],
) -> NarrationCoverage:
    """Atomically retain first successful introductions and ignore repeats.

    Every proposed record is validated before a new coverage object is made.
    A repeated subject retains its first source/node/turn audit record rather
    than pretending a later explanation was its first introduction.
    """
    current = load_narration_coverage(coverage)
    try:
        proposed = tuple(
            record if isinstance(record, IntroductionRecord) else IntroductionRecord.from_dict(record)
            for record in records
        )
    except TypeError as exc:
        raise NarrationCoverageError("records must be iterable") from exc
    # The tuple construction above validates every record before anything is
    # combined, giving a closed, atomic failure path for a mixed batch.
    existing = {(record.subject_kind, record.subject_id) for record in current.introduction_records}
    appended: list[IntroductionRecord] = []
    for record in proposed:
        key = (record.subject_kind, record.subject_id)
        if key not in existing:
            appended.append(record)
            existing.add(key)
    all_records = (*current.introduction_records, *appended)
    return NarrationCoverage(
        schema_version=SCHEMA_VERSION,
        introduced_craft_ids=tuple(record.subject_id for record in all_records if record.subject_kind == "craft"),
        introduced_ornament_ids=tuple(record.subject_id for record in all_records if record.subject_kind == "ornament"),
        introduction_records=all_records,
    )


def clear_narration_coverage(_: NarrationCoverage | dict[str, Any] | None = None) -> NarrationCoverage:
    """Return a new empty session-scoped coverage snapshot."""
    return empty_narration_coverage()


def is_craft_introduced(coverage: NarrationCoverage | dict[str, Any] | None, craft_id: str) -> bool:
    return _clean_text(craft_id, "craft_id") in load_narration_coverage(coverage).introduced_craft_ids


def is_ornament_introduced(coverage: NarrationCoverage | dict[str, Any] | None, ornament_id: str) -> bool:
    return _clean_text(ornament_id, "ornament_id") in load_narration_coverage(coverage).introduced_ornament_ids
