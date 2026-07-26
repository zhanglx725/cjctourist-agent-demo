"""B1 deterministic candidate selection for one approved guide-stop program.

This module only decides *which* reviewed ornaments are worth covering at a
stop.  It does not route visitors, call RAG/LLMs, or write TourState.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from tour_qa import load_guide_cards


VALID_DETAIL_LEVELS = {"short", "standard", "deep"}
DETAIL_ITEM_LIMITS = {"short": 1, "standard": 2, "deep": 3}
MIN_ITEM_SECONDS = 45


class GuideProgramError(ValueError):
    """Raised when a StopProgram cannot use reviewed point-card data."""


@dataclass(frozen=True)
class SelectedItem:
    ornament_id: str
    name: str
    craft: str
    role: str
    planned_seconds: int
    selection_reason: str
    rag_query_hints: tuple[str, ...]
    # B1 keeps the future card interface visible but intentionally empty.
    research_summary_card_ids: tuple[str, ...] = ()
    comparison_card_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rag_query_hints"] = list(self.rag_query_hints)
        data["research_summary_card_ids"] = list(self.research_summary_card_ids)
        data["comparison_card_ids"] = list(self.comparison_card_ids)
        return data


@dataclass(frozen=True)
class StopProgram:
    node_id: str
    display_name: str
    budget_seconds: int
    interests: tuple[str, ...]
    detail_level: str
    selected_items: tuple[SelectedItem, ...]
    candidate_count: int
    selection_strategy: str = "b1_deterministic_interest_then_stable_id"
    status: str = "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "interests": list(self.interests),
            "selected_items": [item.to_dict() for item in self.selected_items],
        }


def _normalise_interests(interests: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(sorted({str(item).strip() for item in (interests or []) if str(item).strip()}))


def _interest_score(ornament: dict[str, str], interests: tuple[str, ...]) -> int:
    """Small transparent B1 score; B2 will add richer diversity/time policy."""
    name = ornament.get("name", "")
    craft = ornament.get("craft", "")
    score = 0
    story_markers = ("三顾", "三英", "桃园", "赤壁", "孟德", "阿斗", "刘备", "关羽", "张飞")
    auspicious_markers = ("福", "寿", "禄", "瑞", "科", "状元", "凤", "麒麟", "吉")
    for interest in interests:
        if interest and (interest in craft or interest in name):
            score += 100
        if interest == "三国" and any(marker in name for marker in story_markers):
            score += 80
        if interest in {"故事", "人物故事"} and any(marker in name for marker in story_markers):
            score += 50
        if interest in {"吉祥", "吉祥题材"} and any(marker in name for marker in auspicious_markers):
            score += 50
    return score


def _target_count(budget_seconds: int, detail_level: str, candidate_count: int) -> int:
    # B1 only reserves a feasible coarse amount. B2 will later optimize the
    # per-item allocation and observation/interaction portions of the stop.
    budget_limit = max(1, budget_seconds // MIN_ITEM_SECONDS)
    return min(DETAIL_ITEM_LIMITS[detail_level], budget_limit, candidate_count)


def _rag_hints(card: dict[str, Any], ornament: dict[str, str]) -> tuple[str, ...]:
    name = ornament["name"]
    matched = tuple(query for query in card.get("rag_queries", []) if name in query)
    return matched or (f"{name} 是什么装饰",)


def _role(index: int) -> str:
    return ("核心观察", "工艺对照", "延伸观察")[index]


def plan_stop_program(
    node_id: str,
    budget_seconds: int,
    interests: list[str] | tuple[str, ...] | None = None,
    detail_level: str = "standard",
) -> StopProgram:
    """Select one to three reviewed ornaments deterministically for a stop."""
    if not isinstance(budget_seconds, int) or budget_seconds <= 0:
        raise GuideProgramError("budget_seconds 必须为大于 0 的整数")
    if detail_level not in VALID_DETAIL_LEVELS:
        raise GuideProgramError("detail_level 必须为 short、standard 或 deep")
    card = load_guide_cards().get(node_id)
    if card is None:
        raise GuideProgramError("该 node_id 没有已审核点位讲解包")
    candidates = [
        item for item in card.get("ornaments", [])
        if item.get("ornament_id") and item.get("name") and item.get("craft")
    ]
    normalised_interests = _normalise_interests(interests)
    if not candidates:
        return StopProgram(
            node_id=node_id,
            display_name=card.get("display_name", node_id),
            budget_seconds=budget_seconds,
            interests=normalised_interests,
            detail_level=detail_level,
            selected_items=(),
            candidate_count=0,
            status="no_reviewed_candidates",
        )
    ranked = sorted(
        candidates,
        key=lambda item: (-_interest_score(item, normalised_interests), item["ornament_id"]),
    )
    count = _target_count(budget_seconds, detail_level, len(ranked))
    selected = ranked[:count]
    base_seconds, remainder = divmod(budget_seconds, count)
    items = tuple(
        SelectedItem(
            ornament_id=item["ornament_id"],
            name=item["name"],
            craft=item["craft"],
            role=_role(index),
            planned_seconds=base_seconds + (1 if index < remainder else 0),
            selection_reason=(
                "匹配游客兴趣：" + "、".join(normalised_interests)
                if _interest_score(item, normalised_interests) > 0
                else "按已审核候选的稳定 ID 顺序选取代表对象"
            ),
            rag_query_hints=_rag_hints(card, item),
        )
        for index, item in enumerate(selected)
    )
    return StopProgram(
        node_id=node_id,
        display_name=card.get("display_name", node_id),
        budget_seconds=budget_seconds,
        interests=normalised_interests,
        detail_level=detail_level,
        selected_items=items,
        candidate_count=len(candidates),
    )
