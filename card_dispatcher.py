"""P3-03 deterministic, read-only enhancement-card candidate dispatcher.

The dispatcher never renders card text and never writes route, TourState,
VisitorProfile, StopProgram, or NarrationCoverage.  It only returns ordered,
auditable candidates that a later P3-04 composer may choose to omit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from guide_program_planner import StopProgram
from guidance_policy import GuidancePolicy
from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry
from photo_spot_validation import query_available_photo_spots


ROOT = Path(__file__).parent
TERM_ASSOCIATIONS = ROOT / "data" / "chen_clan_academy" / "routes" / "term_stop_associations_v1.json"
RESEARCH_NODE_MAPPING = ROOT / "data" / "chen_clan_academy" / "routes" / "research_card_node_mapping_v1.json"
VALID_JOURNEY_MODES = {"classic", "custom"}


@dataclass(frozen=True)
class CardEnhancementCandidate:
    rank: int
    candidate_type: str
    card_id: str | None
    required: bool
    reason_code: str
    source_refs: tuple[str, ...] = ()
    attribution_required: bool = False
    estimated_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_refs"] = list(self.source_refs)
        return value


@dataclass(frozen=True)
class CardDispatchPlan:
    node_id: str
    journey_mode: str
    remaining_budget_seconds: int
    candidates: tuple[CardEnhancementCandidate, ...]
    rejected_reason_codes: tuple[str, ...]
    read_only: bool = True
    state_writes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "rejected_reason_codes": list(self.rejected_reason_codes),
            "state_writes": list(self.state_writes),
        }


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _term_ids(node_id: str, selected_ornament_ids: set[str]) -> tuple[str, ...]:
    rows = _json(TERM_ASSOCIATIONS).get("associations", [])
    direct = {
        row.get("term_id")
        for row in rows
        if isinstance(row, dict)
        and row.get("node_id") == node_id
        and row.get("association_type") == "direct_craft_observation"
        and row.get("status") == "derived_from_approved_ornament_mapping"
        and any(ornament_id in str(row.get("evidence", "")) for ornament_id in selected_ornament_ids)
    }
    return tuple(sorted(value for value in direct if isinstance(value, str)))


def _research_ids(node_id: str) -> tuple[str, ...]:
    rows = _json(RESEARCH_NODE_MAPPING).get("node_mappings", [])
    for row in rows:
        if isinstance(row, dict) and row.get("node_id") == node_id:
            return tuple(sorted({str(value) for value in row.get("research_summary_card_ids", [])}))
    return ()


def _eligible(card: KnowledgeCard | None, card_type: str) -> bool:
    return bool(
        card
        and card.card_type == card_type
        and card.visitor_visible
        and not card.validation_errors
        and card.runtime_status in {"enabled", "attributed_only"}
        and card.source_refs
    )


def _interest_match(card: KnowledgeCard, interests: tuple[str, ...]) -> bool:
    if not interests:
        return False
    searchable = json.dumps(card.raw_payload, ensure_ascii=False, sort_keys=True)
    return any(interest and interest in searchable for interest in interests)


def dispatch_card_candidates(
    *,
    node_id: str,
    stop_program: StopProgram,
    guidance_policy: GuidancePolicy,
    journey_mode: str,
    explicit_interests: tuple[str, ...] | list[str] = (),
    remaining_budget_seconds: int,
    explicit_photo_intent: bool = False,
    photo_safety_cleared: bool = False,
    registry_loader: Callable[[], Mapping[str, KnowledgeCard]] = build_registry,
    photo_selector: Callable[..., dict[str, Any]] = query_available_photo_spots,
) -> CardDispatchPlan:
    """Return ordered enhancement candidates without rendering or mutation."""
    if node_id != stop_program.node_id:
        raise ValueError("node_id must match StopProgram node_id")
    if journey_mode not in VALID_JOURNEY_MODES:
        raise ValueError("journey_mode must be classic or custom")
    if isinstance(remaining_budget_seconds, bool) or remaining_budget_seconds < 0:
        raise ValueError("remaining_budget_seconds must be non-negative")

    interests = tuple(sorted({str(value).strip() for value in explicit_interests if str(value).strip()}))
    before_program = stop_program.to_dict()
    registry = dict(registry_loader())
    candidates: list[CardEnhancementCandidate] = []
    rejected: set[str] = set()
    available_budget = remaining_budget_seconds

    # The reviewed StopProgram remains the sole object selector.  This marker
    # contains IDs only and cannot become a second factual narration payload.
    if stop_program.selected_items:
        candidates.append(CardEnhancementCandidate(
            rank=0, candidate_type="base_object_facts", card_id=None, required=True,
            reason_code="reviewed_stop_program_objects", estimated_seconds=0,
        ))
    else:
        rejected.add("no_reviewed_base_objects")

    selected_ornament_ids = {item.ornament_id for item in stop_program.selected_items}
    if guidance_policy.term_explanation_enabled and available_budget >= 20:
        for card_id in _term_ids(node_id, selected_ornament_ids):
            card = registry.get(card_id)
            if _eligible(card, "glossary_term"):
                candidates.append(CardEnhancementCandidate(
                    rank=10, candidate_type="term_explanation", card_id=card_id,
                    required=False, reason_code="reviewed_term_at_current_node",
                    source_refs=card.source_refs, estimated_seconds=20,
                ))
                available_budget -= 20
                break
        else:
            rejected.add("no_eligible_term_card")
    else:
        rejected.add("term_policy_or_budget_denied")

    research_allowed = (
        journey_mode == "custom"
        and guidance_policy.research_extension_enabled
        and available_budget >= 40
    )
    if research_allowed:
        for card_id in _research_ids(node_id):
            card = registry.get(card_id)
            if _eligible(card, "research_summary") and _interest_match(card, interests):
                candidates.append(CardEnhancementCandidate(
                    rank=20, candidate_type="research_summary", card_id=card_id,
                    required=False, reason_code="attributed_research_interest_match",
                    source_refs=card.source_refs, attribution_required=True,
                    estimated_seconds=40,
                ))
                available_budget -= 40
                break
        else:
            rejected.add("no_eligible_research_interest_match")
    else:
        rejected.add("research_mode_policy_or_budget_denied")

    comparison_ids = tuple(sorted({
        card_id
        for item in stop_program.selected_items
        for card_id in item.comparison_card_ids
    }))
    comparison_allowed = (
        journey_mode == "custom"
        and guidance_policy.comparison_enabled
        and available_budget >= 40
    )
    if comparison_allowed:
        for card_id in comparison_ids:
            card = registry.get(card_id)
            if _eligible(card, "comparison"):
                candidates.append(CardEnhancementCandidate(
                    rank=30, candidate_type="comparison", card_id=card_id,
                    required=False, reason_code="explicit_stop_program_comparison",
                    source_refs=card.source_refs, attribution_required=True,
                    estimated_seconds=40,
                ))
                available_budget -= 40
                break
        else:
            rejected.add("no_explicit_eligible_comparison_card")
    else:
        rejected.add("comparison_mode_policy_or_budget_denied")

    if explicit_photo_intent and photo_safety_cleared and available_budget >= 20:
        selection = photo_selector(node_id=node_id, audience_mode=guidance_policy.audience_mode, themes=interests)
        if selection.get("available") and selection.get("photo_spot", {}).get("node_id") == node_id:
            photo_id = selection["photo_spot"].get("photo_spot_id")
            if isinstance(photo_id, str):
                candidates.append(CardEnhancementCandidate(
                    rank=40, candidate_type="photo_spot", card_id=photo_id,
                    required=False, reason_code="explicit_photo_intent_passed_safety_and_node_gate",
                    estimated_seconds=20,
                ))
                available_budget -= 20
            else:
                rejected.add("photo_gate_returned_invalid_candidate")
        else:
            rejected.add("photo_safety_or_node_gate_denied")
    else:
        rejected.add("photo_intent_safety_or_budget_denied")

    if stop_program.to_dict() != before_program:
        raise RuntimeError("CardDispatcher mutated StopProgram")
    ordered = tuple(sorted(candidates, key=lambda item: (item.rank, item.card_id or "")))
    return CardDispatchPlan(
        node_id=node_id,
        journey_mode=journey_mode,
        remaining_budget_seconds=remaining_budget_seconds,
        candidates=ordered,
        rejected_reason_codes=tuple(sorted(rejected)),
    )
