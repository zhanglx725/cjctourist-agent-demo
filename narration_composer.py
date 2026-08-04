"""P3-04 facts-only composition and shared visitor/TTS layout."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Callable, Mapping

from card_dispatcher import CardDispatchPlan, CardEnhancementCandidate
from controlled_knowledge_query import PUBLIC_VISITOR_SAFE_FALLBACK, public_visitor_message_or_fallback
from guide_program_planner import StopProgram
from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry
from narration_rendering import NarrationRenderResult
from photo_spot_validation import query_available_photo_spots


MAX_VISITOR_CHARS = 1800
MAX_ENHANCEMENTS = 2
_LIST_PREFIX = re.compile(r"(?m)^\s*(?:[-*+] |\d+[.)、]\s*)")


@dataclass(frozen=True)
class ComposedNarration:
    visitor_message: str
    tts_text: str
    used_card_ids: tuple[str, ...]
    used_source_refs: tuple[str, ...]
    omitted_card_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    layout_version: str = "p3_narration_layout_v1"
    state_writes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("used_card_ids", "used_source_refs", "omitted_card_ids", "warnings", "state_writes"):
            value[key] = list(value[key])
        return value


def _flat(text: str) -> str:
    paragraphs = []
    for value in re.split(r"\n\s*\n", str(text or "").strip()):
        cleaned = _LIST_PREFIX.sub("", " ".join(value.split())).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return "\n\n".join(paragraphs)


def _eligible(candidate: CardEnhancementCandidate, card: KnowledgeCard | None, expected_type: str) -> bool:
    return bool(
        candidate.card_id
        and card
        and card.card_id == candidate.card_id
        and card.card_type == expected_type
        and card.runtime_status in {"enabled", "attributed_only"}
        and not card.validation_errors
        and card.source_refs
        and tuple(candidate.source_refs) == tuple(card.source_refs)
    )


def _term_text(candidate: CardEnhancementCandidate, card: KnowledgeCard | None) -> str | None:
    if not _eligible(candidate, card, "glossary_term"):
        return None
    raw = card.raw_payload
    name = str(raw.get("zh") or "").strip()
    definition = str(raw.get("short_definition_zh") or "").strip()
    if not name or not definition:
        return None
    return f"术语“{name}”：{definition}"


def _research_attribution(raw: dict[str, Any]) -> str | None:
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    citation = str(source.get("citation") or "").strip()
    author = citation.split(".", 1)[0].strip(" ，,")
    if not author:
        return None
    year = re.search(r"\((\d{4})\)", citation)
    return f"{author}{f'（{year.group(1)}）' if year else ''}的研究"


def _research_text(candidate: CardEnhancementCandidate, card: KnowledgeCard | None) -> str | None:
    if not candidate.attribution_required or not _eligible(candidate, card, "research_summary"):
        return None
    raw = card.raw_payload
    if raw.get("status") != "reviewed":
        return None
    attribution = _research_attribution(raw)
    takeaway = str(raw.get("guide_safe_takeaway") or "").strip()
    limits = raw.get("agreement_and_limits") if isinstance(raw.get("agreement_and_limits"), dict) else {}
    limitation = str(limits.get("limits") or "").strip()
    if not attribution or not takeaway or not limitation:
        return None
    return f"据{attribution}，{takeaway} 这一观察受以下范围限制：{limitation}"


def _comparison_text(candidate: CardEnhancementCandidate, card: KnowledgeCard | None) -> str | None:
    if not candidate.attribution_required or not _eligible(candidate, card, "comparison"):
        return None
    raw = card.raw_payload
    if raw.get("claim_strength") not in {"research_only", "cautious"}:
        return None
    conclusion = str(raw.get("visitor_conclusion_zh") or "").strip()
    scope = str(raw.get("scope_zh") or "").strip()
    limitation = str(raw.get("limitations_zh") or "").strip()
    if not conclusion or not scope or not limitation:
        return None
    return f"相关比较研究认为：{conclusion} 比较范围仅限于：{scope} 使用时还需注意：{limitation}"


def _photo_text(
    candidate: CardEnhancementCandidate,
    card: KnowledgeCard | None,
    *,
    node_id: str,
    photo_selector: Callable[..., dict[str, Any]],
) -> str | None:
    if not candidate.card_id or not card or card.card_type != "photo_spot_card" or card.validation_errors:
        return None
    selection = photo_selector(node_id=node_id, themes=())
    selected = selection.get("photo_spot", {}) if selection.get("available") else {}
    if selected.get("photo_spot_id") != candidate.card_id or selected.get("node_id") != node_id:
        return None
    raw = card.raw_payload
    title = str(raw.get("title_zh") or "").strip()
    capture = str(raw.get("recommended_capture_zh") or "").strip()
    boundary = str(raw.get("boundaries_zh") or "").strip()
    if not title or not capture or not boundary:
        return None
    return f"拍摄建议“{title}”：{capture} 安全边界：{boundary}"


def _insert_before_next(base: str, enhancement: str | None) -> str:
    marker = "【下一步】"
    if not enhancement:
        return base
    block = f"【可选深入】\n\n{enhancement}"
    if marker not in base:
        return f"{base}\n\n{block}"
    before, after = base.split(marker, 1)
    return f"{before.rstrip()}\n\n{block}\n\n{marker}{after}"


def compose_narration(
    *,
    stop_program: StopProgram,
    base_render: NarrationRenderResult,
    dispatch_plan: CardDispatchPlan,
    registry_loader: Callable[[], Mapping[str, KnowledgeCard]] = build_registry,
    photo_selector: Callable[..., dict[str, Any]] = query_available_photo_spots,
) -> ComposedNarration:
    """Compose one safe body for both display and speech; never mutate inputs."""
    if stop_program.node_id != dispatch_plan.node_id:
        raise ValueError("dispatch node must match StopProgram node")
    before_program = stop_program.to_dict()
    before_render = base_render.to_dict()
    before_dispatch = dispatch_plan.to_dict()
    registry = dict(registry_loader())
    base = _flat(base_render.visitor_message)
    warnings: list[str] = []
    used_ids: list[str] = []
    used_sources: set[str] = set(base_render.used_source_ids)
    omitted_ids: list[str] = []
    enhancement_texts: list[str] = []
    enhancement_seconds = 0

    for candidate in dispatch_plan.candidates:
        if candidate.required or candidate.card_id is None:
            continue
        if len(enhancement_texts) >= MAX_ENHANCEMENTS:
            omitted_ids.append(candidate.card_id)
            warnings.append("enhancement_count_limit")
            continue
        if enhancement_seconds + candidate.estimated_seconds > dispatch_plan.remaining_budget_seconds:
            omitted_ids.append(candidate.card_id)
            warnings.append("enhancement_budget_limit")
            continue
        card = registry.get(candidate.card_id)
        text = None
        if candidate.candidate_type == "term_explanation":
            text = _term_text(candidate, card)
        elif candidate.candidate_type == "research_summary":
            text = _research_text(candidate, card)
        elif candidate.candidate_type == "comparison":
            text = _comparison_text(candidate, card)
        elif candidate.candidate_type == "photo_spot":
            text = _photo_text(candidate, card, node_id=stop_program.node_id, photo_selector=photo_selector)
        if not text:
            omitted_ids.append(candidate.card_id)
            warnings.append(f"{candidate.candidate_type}_revalidation_failed")
            continue
        projected = _insert_before_next(base, "\n\n".join([*enhancement_texts, text]))
        if len(projected) > MAX_VISITOR_CHARS:
            omitted_ids.append(candidate.card_id)
            warnings.append("visitor_length_limit")
            continue
        enhancement_texts.append(text)
        enhancement_seconds += candidate.estimated_seconds
        used_ids.append(candidate.card_id)
        used_sources.update(card.source_refs if card else ())

    composed = _insert_before_next(base, "\n\n".join(enhancement_texts) if enhancement_texts else None)
    public = public_visitor_message_or_fallback(composed, fallback=PUBLIC_VISITOR_SAFE_FALLBACK)
    if public == PUBLIC_VISITOR_SAFE_FALLBACK and composed != PUBLIC_VISITOR_SAFE_FALLBACK:
        warnings.append("public_boundary_fallback")

    if stop_program.to_dict() != before_program or base_render.to_dict() != before_render or dispatch_plan.to_dict() != before_dispatch:
        raise RuntimeError("NarrationComposer mutated an input")
    return ComposedNarration(
        visitor_message=public,
        tts_text=public,
        used_card_ids=tuple(used_ids),
        used_source_refs=tuple(sorted(used_sources)),
        omitted_card_ids=tuple(omitted_ids),
        warnings=tuple(sorted(set(warnings))),
    )
