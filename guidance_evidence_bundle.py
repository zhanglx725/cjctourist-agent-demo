"""E5-A2 structured, evidence-grounded inputs for later narration.

This module does not write NarrationCoverage or AgentState.  It turns an
already-audited StopProgram plus a read-only coverage snapshot into separated
craft, ornament, and location packets.  The caller supplies the established
RAG callable; no second index or LLM is created here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from guide_program_planner import SelectedItem, StopProgram
from narration_coverage import NarrationCoverage, is_craft_introduced, is_ornament_introduced, load_narration_coverage
from knowledge_evidence_policy import optional_narration_evidence_is_safe
from point_knowledge_profiles import OPTIONAL_DOCUMENTS, optional_context_query, point_knowledge_profile
from tour_qa import load_guide_cards, parse_rag_payload


CRAFT_DOCUMENTS = frozenset({
    "07_ornament_crafts.md",
    "11_architectural_conservation.md",
    "12_craft_process_and_transmission.md",
})
ORNAMENT_DOCUMENTS = frozenset({
    "02_history_architecture.md",
    "08_ornament_items.md",
    "09_ornament_locations.md",
    "10_people_builders_craftspeople.md",
    "11_architectural_conservation.md",
    "12_craft_process_and_transmission.md",
    "13_literary_citation_cards.md",
    "14_students_examinations_and_education.md",
})
VALID_MAPPING_DECISIONS = frozenset({"change", "add_node"})


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _stable_source_ids(evidence: tuple[Mapping[str, Any], ...]) -> tuple[str, ...]:
    return tuple(sorted({source.strip() for entry in evidence for source in entry.get("source_ids", ()) if isinstance(source, str) and source.strip()}))


@dataclass(frozen=True)
class EvidencePacket:
    """One typed evidence result, retaining every qualifying evidence block."""

    evidence_kind: str
    subject_id: str
    query: str
    evidence: tuple[Mapping[str, Any], ...]
    source_ids: tuple[str, ...]
    retrieval_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_kind": self.evidence_kind,
            "subject_id": self.subject_id,
            "query": self.query,
            "evidence": [_thaw(entry) for entry in self.evidence],
            "source_ids": list(self.source_ids),
            "retrieval_error": self.retrieval_error,
        }


@dataclass(frozen=True)
class LocationEvidence:
    ornament_id: str
    node_id: str
    raw_location: str | None
    location_source: str | None
    mapping_decision: str | None
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ornament_id": self.ornament_id,
            "node_id": self.node_id,
            "raw_location": self.raw_location,
            "location_source": self.location_source,
            "mapping_decision": self.mapping_decision,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class CoverageCandidate:
    subject_kind: str
    subject_id: str
    source_ids: tuple[str, ...]
    node_id: str
    evidence_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "source_ids": list(self.source_ids),
            "node_id": self.node_id,
            "evidence_kind": self.evidence_kind,
        }


@dataclass(frozen=True)
class GuidanceEvidenceBundle:
    node_id: str
    craft_overviews: Mapping[str, EvidencePacket]
    ornament_details: Mapping[str, EvidencePacket]
    optional_context: EvidencePacket | None
    location_evidence: Mapping[str, LocationEvidence]
    coverage_status: Mapping[str, Mapping[str, str]]
    coverage_candidates: tuple[CoverageCandidate, ...]
    source_ids: tuple[str, ...]

    @property
    def evidence_by_item(self) -> dict[str, list[dict[str, Any]]]:
        """Compatibility view for B3 consumers; no existing interface changes."""
        return {
            ornament_id: [_thaw(entry) for entry in packet.evidence]
            for ornament_id, packet in self.ornament_details.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "craft_overviews": {key: packet.to_dict() for key, packet in self.craft_overviews.items()},
            "ornament_details": {key: packet.to_dict() for key, packet in self.ornament_details.items()},
            "optional_context": self.optional_context.to_dict() if self.optional_context else None,
            "location_evidence": {key: packet.to_dict() for key, packet in self.location_evidence.items()},
            "coverage_status": {kind: dict(status) for kind, status in self.coverage_status.items()},
            "coverage_candidates": [candidate.to_dict() for candidate in self.coverage_candidates],
            "source_ids": list(self.source_ids),
            "evidence_by_item": self.evidence_by_item,
        }


def _document_name(entry: Mapping[str, Any]) -> str:
    return Path(str(entry.get("document", ""))).name


def _title_parts(entry: Mapping[str, Any]) -> tuple[str, ...]:
    raw = entry.get("title_path", ())
    return tuple(str(part).strip() for part in raw if isinstance(part, str) and part.strip()) if isinstance(raw, (tuple, list)) else ()


def _has_sources(entry: Mapping[str, Any]) -> bool:
    return bool(_stable_source_ids((entry,)))


def optional_dimension_id(entry: Mapping[str, Any]) -> str:
    """Stable internal topic ID used only for cross-stop repetition control."""
    raw = "|".join((
        _document_name(entry),
        "/".join(_title_parts(entry)),
    ))
    return "knowledge_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _craft_evidence_matches(entry: Mapping[str, Any], craft: str) -> bool:
    if _document_name(entry) not in CRAFT_DOCUMENTS or not _has_sources(entry):
        return False
    titles = _title_parts(entry)
    return craft in titles or craft in str(entry.get("content", ""))


def _ornament_evidence_matches(entry: Mapping[str, Any], item: SelectedItem) -> bool:
    if _document_name(entry) not in ORNAMENT_DOCUMENTS or not _has_sources(entry):
        return False
    # The item title remains the audited identity boundary.  Newly curated
    # documents prefix headings with card numbers or section labels, so accept
    # a title component containing the exact reviewed object name; a mention
    # in body content alone is still insufficient.
    return any(item.name in title for title in _title_parts(entry))


def _optional_evidence_matches(entry: Mapping[str, Any], program: StopProgram) -> bool:
    mutable_entry = dict(entry)
    if (
        _document_name(entry) not in OPTIONAL_DOCUMENTS
        or not _has_sources(entry)
        or not optional_narration_evidence_is_safe(mutable_entry)
    ):
        return False
    profile = point_knowledge_profile(program.node_id)
    if profile is None:
        return False
    haystack = " ".join((*_title_parts(entry), str(entry.get("content", ""))))
    anchors = {
        program.display_name,
        *(item.name for item in program.selected_items),
        *(item.craft for item in program.selected_items),
        *profile.visible_components,
    }
    domain_terms = {
        term
        for term in (
            "保护", "修缮", "制作", "工序", "传承", "工匠", "文学", "诗经",
            "三国演义", "科举", "应试", "书院", "教育", "城市", "礼制", "空间",
        )
        if any(term in dimension for dimension in profile.optional_dimensions)
    }
    return any(anchor and anchor in haystack for anchor in (*anchors, *domain_terms))


def _search_packet(
    *,
    evidence_kind: str,
    subject_id: str,
    query: str,
    predicate: Callable[[Mapping[str, Any]], bool],
    rag_search: Callable[[str], str],
) -> EvidencePacket:
    try:
        payload = parse_rag_payload(rag_search(query))
    except Exception as exc:  # Caller must be able to continue other packets.
        return EvidencePacket(evidence_kind, subject_id, query, (), (), retrieval_error=str(exc))
    accepted = tuple(
        _freeze(deepcopy(entry))
        for entry in payload.get("evidence", [])
        if isinstance(entry, dict) and predicate(entry)
    )
    return EvidencePacket(evidence_kind, subject_id, query, accepted, _stable_source_ids(accepted))


def _reviewed_mapping(item: SelectedItem, node_id: str) -> LocationEvidence:
    cards = load_guide_cards()
    card = cards.get(node_id, {})
    matched = next(
        (
            ornament for ornament in card.get("ornaments", [])
            if isinstance(ornament, dict) and ornament.get("ornament_id") == item.ornament_id
        ),
        None,
    )
    decision = matched.get("mapping_decision") if matched else None
    raw_location = item.raw_location.strip() if isinstance(item.raw_location, str) and item.raw_location.strip() else None
    valid = bool(
        matched
        and raw_location
        and matched.get("final_node_id") == node_id
        and matched.get("mapping_decision") in VALID_MAPPING_DECISIONS
        and item.location_source
    )
    return LocationEvidence(
        ornament_id=item.ornament_id,
        node_id=node_id,
        raw_location=raw_location if valid else None,
        location_source=item.location_source if valid else None,
        mapping_decision=decision if valid else None,
        valid=valid,
    )


def build_guidance_evidence_bundle(
    program: StopProgram,
    coverage: NarrationCoverage | dict[str, Any] | None,
    rag_search: Callable[[str], str],
) -> GuidanceEvidenceBundle:
    """Collect typed evidence without rendering prose or mutating any state."""
    loaded_coverage = load_narration_coverage(coverage)
    crafts = tuple(dict.fromkeys(item.craft for item in program.selected_items))
    craft_status = {
        craft: "repeat" if is_craft_introduced(loaded_coverage, craft) else "first_introduction"
        for craft in crafts
    }
    ornament_status = {
        item.ornament_id: "repeat" if is_ornament_introduced(loaded_coverage, item.ornament_id) else "first_introduction"
        for item in program.selected_items
    }

    craft_packets: dict[str, EvidencePacket] = {}
    ornament_packets: dict[str, EvidencePacket] = {}
    locations: dict[str, LocationEvidence] = {}
    candidates: list[CoverageCandidate] = []

    for craft in crafts:
        if craft_status[craft] == "repeat":
            continue
        query = f"{craft} 定义 材料 技法 建筑位置 特点 制作工序 保护修缮 工艺传承"
        packet = _search_packet(
            evidence_kind="craft_overview",
            subject_id=craft,
            query=query,
            predicate=lambda entry, expected=craft: _craft_evidence_matches(entry, expected),
            rag_search=rag_search,
        )
        craft_packets[craft] = packet
        if packet.source_ids:
            candidates.append(CoverageCandidate("craft", craft, packet.source_ids, program.node_id, "craft_overview"))

    for item in program.selected_items:
        query = f"{item.ornament_id} {item.name} {item.craft} 陈家祠 建筑装饰"
        packet = _search_packet(
            evidence_kind="ornament_detail",
            subject_id=item.ornament_id,
            query=query,
            predicate=lambda entry, expected=item: _ornament_evidence_matches(entry, expected),
            rag_search=rag_search,
        )
        ornament_packets[item.ornament_id] = packet
        locations[item.ornament_id] = _reviewed_mapping(item, program.node_id)
        if packet.source_ids:
            candidates.append(CoverageCandidate("ornament", item.ornament_id, packet.source_ids, program.node_id, "ornament_detail"))

    context_query = optional_context_query(
        program.node_id,
        program.display_name,
        object_names=tuple(item.name for item in program.selected_items),
        crafts=crafts,
    )
    optional_context = (
        _search_packet(
            evidence_kind="optional_point_context",
            subject_id=program.node_id,
            query=context_query,
            predicate=lambda entry: _optional_evidence_matches(entry, program),
            rag_search=rag_search,
        )
        if context_query else None
    )
    introduced_dimensions = {
        record.subject_id
        for record in loaded_coverage.introduction_records
        if record.subject_kind == "dimension"
    }
    if optional_context is not None and optional_context.evidence:
        retained = tuple(
            entry for entry in optional_context.evidence
            if optional_dimension_id(entry) not in introduced_dimensions
        )
        optional_context = EvidencePacket(
            optional_context.evidence_kind,
            optional_context.subject_id,
            optional_context.query,
            retained,
            _stable_source_ids(retained),
            optional_context.retrieval_error,
        )
        for entry in retained:
            candidates.append(CoverageCandidate(
                "dimension",
                optional_dimension_id(entry),
                _stable_source_ids((entry,)),
                program.node_id,
                "optional_point_context",
            ))

    all_packets = (
        *craft_packets.values(),
        *ornament_packets.values(),
        *((optional_context,) if optional_context else ()),
    )
    source_ids = tuple(sorted({source for packet in all_packets for source in packet.source_ids}))
    return GuidanceEvidenceBundle(
        node_id=program.node_id,
        craft_overviews=MappingProxyType(craft_packets),
        ornament_details=MappingProxyType(ornament_packets),
        optional_context=optional_context,
        location_evidence=MappingProxyType(locations),
        coverage_status=MappingProxyType({"craft": MappingProxyType(craft_status), "ornament": MappingProxyType(ornament_status)}),
        coverage_candidates=tuple(candidates),
        source_ids=source_ids,
    )
