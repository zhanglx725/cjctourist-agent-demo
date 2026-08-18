"""Deterministic P4-02 visit summary derived from authoritative session state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from narration_coverage import NarrationCoverageError, load_narration_coverage
from visitor_profile import VisitorProfileError, profile_from_dict


GUIDE_CARDS_FILE = Path("data/chen_clan_academy/routes/node_guide_cards_v1.json")


class VisitSummaryError(ValueError):
    pass


@dataclass(frozen=True)
class VisitSummary:
    schema_version: str
    completion_kind: str
    visited_stop_ids: tuple[str, ...]
    visited_stop_names: tuple[str, ...]
    skipped_stop_ids: tuple[str, ...]
    introduced_ornament_ids: tuple[str, ...]
    introduced_ornament_names: tuple[str, ...]
    introduced_craft_ids: tuple[str, ...]
    coverage_status: str
    question_count: int | None
    question_count_status: str
    explicit_interest_ids: tuple[str, ...]
    matched_interest_ids: tuple[str, ...]
    explanation_style: str | None
    interaction_mode: str | None
    knowledge_level: str | None
    profile_basis_status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "visited_stop_ids", "visited_stop_names", "skipped_stop_ids",
            "introduced_ornament_ids", "introduced_ornament_names",
            "introduced_craft_ids",
            "explicit_interest_ids", "matched_interest_ids",
        ):
            value[field] = list(value[field])
        value["visited_stop_count"] = len(self.visited_stop_ids)
        value["introduced_ornament_count"] = len(self.introduced_ornament_ids)
        value["introduced_craft_count"] = len(self.introduced_craft_ids)
        value["title_basis"] = {
            "completion_kind": self.completion_kind,
            "visited_stop_count": len(self.visited_stop_ids),
            "introduced_craft_ids": list(self.introduced_craft_ids),
            "introduced_topic_names": list(self.introduced_ornament_names),
            "content_diversity_count": (
                len(self.introduced_craft_ids) + len(self.introduced_ornament_ids)
            ),
            "question_count": self.question_count,
            "question_count_status": self.question_count_status,
            "explicit_interest_ids": list(self.explicit_interest_ids),
            "matched_interest_ids": list(self.matched_interest_ids),
            "explanation_style": self.explanation_style,
            "interaction_mode": self.interaction_mode,
            "knowledge_level": self.knowledge_level,
            "profile_basis_status": self.profile_basis_status,
        }
        return value


def _reviewed_catalog() -> tuple[dict[str, str], dict[str, tuple[str, str, str]]]:
    try:
        payload = json.loads(GUIDE_CARDS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisitSummaryError("点位资料不可用。") from exc
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list) or not cards:
        raise VisitSummaryError("点位资料为空。")
    stops: dict[str, str] = {}
    ornaments: dict[str, tuple[str, str, str]] = {}
    conflicts: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        node_id = str(card.get("node_id") or "").strip()
        display_name = str(card.get("display_name") or "").strip()
        if node_id and display_name:
            stops[node_id] = display_name
        for item in card.get("ornaments") or []:
            if not isinstance(item, dict):
                continue
            ornament_id = str(item.get("ornament_id") or "").strip()
            name = str(item.get("name") or "").strip()
            craft = str(item.get("craft") or "").strip()
            candidate = (name, craft, node_id)
            if not all(candidate) or not ornament_id:
                continue
            if ornament_id in ornaments and ornaments[ornament_id] != candidate:
                conflicts.add(ornament_id)
            else:
                ornaments[ornament_id] = candidate
    for ornament_id in conflicts:
        ornaments.pop(ornament_id, None)
    if not stops:
        raise VisitSummaryError("点位名称不可用。")
    return stops, ornaments


def build_visit_summary(
    tour_state: dict[str, Any] | None,
    narration_coverage: dict[str, Any] | None,
    question_log: list[dict[str, Any]] | None = None,
    visitor_profile: dict[str, Any] | None = None,
) -> VisitSummary:
    if not isinstance(tour_state, dict) or tour_state.get("route_status") != "completed":
        raise VisitSummaryError("只有已结束的游览才能生成总结。")
    visited = tuple(dict.fromkeys(tour_state.get("visited_stop_ids") or []))
    skipped = tuple(dict.fromkeys(tour_state.get("skipped_stop_ids") or []))
    route = tuple(tour_state.get("route_stop_ids") or [])
    if not all(isinstance(item, str) and item for item in (*visited, *skipped, *route)):
        raise VisitSummaryError("TourState 点位记录无效。")
    if set(visited).intersection(skipped) or not set(visited).issubset(route):
        raise VisitSummaryError("TourState 完成记录不一致。")
    stops, ornament_catalog = _reviewed_catalog()
    if any(node_id not in stops for node_id in visited):
        raise VisitSummaryError("已访问点缺少可用名称。")
    completion_kind = (
        "completed_all_stops"
        if not (tour_state.get("remaining_stop_ids") or [])
        else "finished_early"
    )
    coverage_status = "available"
    accepted_records = []
    try:
        coverage = load_narration_coverage(narration_coverage)
        accepted_records = [
            record for record in coverage.introduction_records
            if record.introduced_by in {
                "stop_guidance", "narration_commit", "deterministic_narration_fallback",
            } and record.node_id in visited
        ]
    except NarrationCoverageError:
        coverage_status = "unavailable"

    ornament_ids: list[str] = []
    craft_ids: list[str] = []
    if coverage_status == "available":
        for record in accepted_records:
            if record.subject_kind == "craft" and record.subject_id not in craft_ids:
                craft_ids.append(record.subject_id)
            if record.subject_kind != "ornament" or record.subject_id in ornament_ids:
                continue
            mapped = ornament_catalog.get(record.subject_id)
            if mapped is None or mapped[2] != record.node_id:
                continue
            ornament_ids.append(record.subject_id)
            if mapped[1] not in craft_ids:
                craft_ids.append(mapped[1])

    visited_names = tuple(stops[node_id] for node_id in visited)
    ornament_names = tuple(ornament_catalog[item][0] for item in ornament_ids)
    opening = (
        f"本次完成了 {len(visited)} 个正式讲解点的参观。"
        if completion_kind == "completed_all_stops"
        else f"本次提前结束，共完成了 {len(visited)} 个正式讲解点的参观。"
    )
    if coverage_status == "unavailable":
        detail = "讲解覆盖记录当前不可用，因此不报告具体工艺或题材数量。"
    elif not ornament_ids and not craft_ids:
        detail = "本轮没有可确认的成功点位讲解覆盖记录。"
    else:
        parts = []
        if craft_ids:
            parts.append("成功讲过的工艺包括" + "、".join(craft_ids))
        if ornament_names:
            parts.append("涉及的题材或构件包括" + "、".join(ornament_names))
        detail = "；".join(parts) + "。"
    question_count_status = "available"
    question_count: int | None = 0
    if not isinstance(question_log, list):
        question_count_status = "unavailable"
        question_count = None
    else:
        route_id = tour_state.get("selected_route_id")
        for index, item in enumerate(question_log, start=1):
            if (
                not isinstance(item, dict)
                or item.get("sequence") != index
                or item.get("route_id") != route_id
                or item.get("node") not in {"tour_qa", "qa_follow_up_detail"}
            ):
                question_count_status = "unavailable"
                question_count = None
                break
        else:
            question_count = len(question_log)
    question_text = (
        f"游览过程中，您共提出了 {question_count} 次问题。"
        if question_count is not None
        else "本轮提问次数记录不可用，因此不报告精确次数。"
    )
    profile_basis_status = "available"
    explicit_interests: tuple[str, ...] = ()
    explanation_style: str | None = None
    interaction_mode: str | None = None
    knowledge_level: str | None = None
    try:
        profile = profile_from_dict(visitor_profile) if visitor_profile is not None else None
    except VisitorProfileError:
        profile = None
        profile_basis_status = "unavailable"
    if profile is not None:
        explicit_interests = tuple(profile.interests)
        # Neutral defaults are deliberately not promoted into achievement
        # signals because the system cannot prove that the visitor chose them.
        explanation_style = (
            profile.explanation_style if profile.explanation_style != "standard" else None
        )
        interaction_mode = (
            profile.interaction_mode if profile.interaction_mode != "normal" else None
        )
        knowledge_level = (
            profile.knowledge_level if profile.knowledge_level != "general" else None
        )
    elif visitor_profile is None:
        profile_basis_status = "unavailable"
    heard_labels = set(craft_ids).union(ornament_names)
    matched_interests = tuple(
        interest for interest in explicit_interests if interest in heard_labels
    )
    return VisitSummary(
        schema_version="visit_summary_v1",
        completion_kind=completion_kind,
        visited_stop_ids=visited,
        visited_stop_names=visited_names,
        skipped_stop_ids=skipped,
        introduced_ornament_ids=tuple(ornament_ids),
        introduced_ornament_names=ornament_names,
        introduced_craft_ids=tuple(craft_ids),
        coverage_status=coverage_status,
        question_count=question_count,
        question_count_status=question_count_status,
        explicit_interest_ids=explicit_interests,
        matched_interest_ids=matched_interests,
        explanation_style=explanation_style,
        interaction_mode=interaction_mode,
        knowledge_level=knowledge_level,
        profile_basis_status=profile_basis_status,
        message=opening + detail + question_text,
    )
