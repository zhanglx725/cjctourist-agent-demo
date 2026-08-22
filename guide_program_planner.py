"""Deterministic StopProgram planning for reviewed guide-stop ornaments.

The planner consumes only the content/explanation budget allocated to one
route stop.  It never consumes walking time, changes a route, calls an LLM or
writes TourState.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from guidance_policy import GuidancePolicy
from point_knowledge_profiles import point_knowledge_profile
from tour_qa import load_guide_cards


VALID_DETAIL_LEVELS = {"short", "standard", "deep"}
POLICY_LENGTH_TO_DETAIL = {"short": "short", "standard": "standard", "detailed": "deep"}

# All B2 policy numbers live here so that later calibration is auditable.
STOP_PROGRAM_POLICY = {
    "budget": {
        "brief_overview_max_seconds": 60,
        "item_count_thresholds": {
            "short": ((0, 1),),
            "standard": ((150, 2), (0, 1)),
            "deep": ((270, 3), (150, 2), (0, 1)),
        },
        "target_item_seconds": {
            "short": (90,),
            "standard": (120, 90),
            "deep": (120, 90, 75),
        },
    },
    "interest": {
        "direct_match": 100,
        "three_kingdoms_story": 80,
        "story": 50,
        "auspicious": 50,
    },
    "diversity": {
        # Diversity only decides between candidates with close relevance.
        "relevance_window": 30,
        "new_craft_bonus": 20,
        "new_theme_bonus": 15,
    },
}

STORY_MARKERS = ("三顾", "三英", "桃园", "赤壁", "孟德", "阿斗", "刘备", "关羽", "张飞", "梁山", "水浒")
AUSPICIOUS_MARKERS = ("福", "寿", "禄", "瑞", "科", "状元", "凤", "麒麟", "吉")


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
    # Future card interfaces remain explicit but intentionally unused in B2.
    research_summary_card_ids: tuple[str, ...] = ()
    comparison_card_ids: tuple[str, ...] = ()
    # Audited display hint only; never used as navigation or fact evidence.
    raw_location: str | None = None
    observation_location: str | None = None
    location_source: str | None = None
    # Present only when this item is deliberately retained to contrast the
    # primary object's craft or treatment; never inferred from raw_location.
    comparison_reason: str | None = None

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
    # The two fields make it explicit that this is not route or walking time.
    budget_scope: str = "stop_explanation_content_only"
    allocated_content_seconds: int = 0
    unallocated_content_seconds: int = 0
    selection_strategy: str = "b2_relevance_diversity_budget"
    status: str = "ready"
    # Derived C6 policy for this program only; it is audit metadata, not a
    # second profile source and not a route or factual-evidence input.
    guidance_policy: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "interests": list(self.interests),
            "selected_items": [item.to_dict() for item in self.selected_items],
        }


def _normalise_interests(interests: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(sorted({str(item).strip() for item in (interests or []) if str(item).strip()}))


def _theme(ornament: dict[str, str]) -> str:
    name = ornament.get("name", "")
    if any(marker in name for marker in STORY_MARKERS):
        return "story"
    if any(marker in name for marker in AUSPICIOUS_MARKERS):
        return "auspicious"
    return f"craft:{ornament.get('craft', '')}"


def _interest_score(ornament: dict[str, str], interests: tuple[str, ...]) -> int:
    """Transparent relevance score; it cannot introduce unreviewed objects."""
    name = ornament.get("name", "")
    craft = ornament.get("craft", "")
    policy = STOP_PROGRAM_POLICY["interest"]
    score = 0
    for interest in interests:
        if interest and (interest in craft or interest in name):
            score += policy["direct_match"]
        if interest == "三国" and any(marker in name for marker in STORY_MARKERS[:9]):
            score += policy["three_kingdoms_story"]
        if interest in {"故事", "人物故事"} and any(marker in name for marker in STORY_MARKERS):
            score += policy["story"]
        if interest in {"吉祥", "吉祥题材"} and any(marker in name for marker in AUSPICIOUS_MARKERS):
            score += policy["auspicious"]
    return score


def _target_count(budget_seconds: int, detail_level: str, candidate_count: int) -> int:
    thresholds = STOP_PROGRAM_POLICY["budget"]["item_count_thresholds"][detail_level]
    desired = next(count for minimum, count in thresholds if budget_seconds >= minimum)
    return min(desired, candidate_count)


def _coerce_guidance_policy(value: GuidancePolicy | dict[str, Any] | None) -> GuidancePolicy | None:
    if value is None:
        return None
    if isinstance(value, GuidancePolicy):
        return value
    if isinstance(value, dict):
        try:
            return GuidancePolicy(**value)
        except TypeError as exc:
            raise GuideProgramError("guidance_policy 结构无效") from exc
    raise GuideProgramError("guidance_policy 必须是 GuidancePolicy、字典或 None")


def _select_diverse_candidates(
    candidates: list[dict[str, str]], interests: tuple[str, ...], count: int
) -> list[dict[str, str]]:
    """Select relevance first, then diversify only inside a close-score window."""
    remaining = sorted(candidates, key=lambda item: (-_interest_score(item, interests), item["ornament_id"]))
    selected: list[dict[str, str]] = []
    seen_crafts: set[str] = set()
    seen_themes: set[str] = set()
    diversity = STOP_PROGRAM_POLICY["diversity"]

    while remaining and len(selected) < count:
        best_relevance = _interest_score(remaining[0], interests)
        close = [
            item for item in remaining
            if best_relevance - _interest_score(item, interests) <= diversity["relevance_window"]
        ]

        def ranking_key(item: dict[str, str]) -> tuple[int, int, str]:
            relevance = _interest_score(item, interests)
            diversity_bonus = 0
            if item["craft"] not in seen_crafts:
                diversity_bonus += diversity["new_craft_bonus"]
            if _theme(item) not in seen_themes:
                diversity_bonus += diversity["new_theme_bonus"]
            return (-(relevance + diversity_bonus), -relevance, item["ornament_id"])

        chosen = min(close, key=ranking_key)
        selected.append(chosen)
        seen_crafts.add(chosen["craft"])
        seen_themes.add(_theme(chosen))
        remaining.remove(chosen)
    return selected


def _allocate_item_seconds(budget_seconds: int, detail_level: str, count: int) -> tuple[int, ...]:
    """Allocate explanation seconds only; never exceeds the supplied budget."""
    if budget_seconds <= STOP_PROGRAM_POLICY["budget"]["brief_overview_max_seconds"]:
        return (budget_seconds,)
    targets = STOP_PROGRAM_POLICY["budget"]["target_item_seconds"][detail_level][:count]
    target_total = sum(targets)
    if budget_seconds >= target_total:
        return tuple(targets)

    # Deterministic proportional downscaling when a valid item count has less
    # than its preferred teaching duration.  Remainders go by stable order.
    base = [(budget_seconds * target) // target_total for target in targets]
    for index in range(budget_seconds - sum(base)):
        base[index % count] += 1
    return tuple(base)


def _rag_hints(card: dict[str, Any], ornament: dict[str, str]) -> tuple[str, ...]:
    name = ornament["name"]
    matched = tuple(query for query in card.get("rag_queries", []) if name in query)
    return matched or (f"{name} 是什么装饰",)


def _role(index: int, budget_seconds: int, selected: list[dict[str, str]]) -> str:
    if budget_seconds <= STOP_PROGRAM_POLICY["budget"]["brief_overview_max_seconds"]:
        return "简短概览"
    if index == 0:
        return "核心观察"
    if index == 1 and selected[index]["craft"] != selected[0]["craft"]:
        return "工艺对照"
    return "补充观察" if index == 1 else "延伸观察"


def _comparison_reason(index: int, selected: list[dict[str, str]]) -> str | None:
    """Explain a non-primary craft without changing its selection score."""
    if index and selected[index]["craft"] != selected[0]["craft"]:
        return (
            f"与核心对象的{selected[0]['craft']}作工艺对照，"
            f"帮助观察两类材料和构件处理的差异"
        )
    return None


def _selection_reason(ornament: dict[str, str], interests: tuple[str, ...], index: int) -> str:
    if _interest_score(ornament, interests) > 0:
        return f"匹配游客兴趣：{'、'.join(interests)}"
    if index:
        return "在相关性接近的已审核候选中，优先补充不同工艺或题材"
    return "按已审核候选的相关性与稳定 ID 顺序选取核心对象"


def _is_coarse_location(raw_location: str, display_name: str) -> bool:
    """Whether a location adds no safe observation detail beyond the stop."""
    normalized = raw_location.strip()
    return not normalized or normalized in {display_name, "本点", "当前点", "此处", "这里"}


def _location_metadata(
    ornament: dict[str, Any], node_id: str, display_name: str
) -> tuple[str | None, str | None, str | None]:
    """Return a safe hint only when the reviewed mapping proves this node.

    No direction, height, reachability, visibility or other spatial fact is
    inferred from the raw reviewer wording.
    """
    raw_location = str(ornament.get("raw_location", "")).strip()
    approved = (
        ornament.get("final_node_id") == node_id
        and ornament.get("mapping_decision") in {"change", "add_node"}
        and ornament.get("mapping_source")
    )
    if not approved or _is_coarse_location(raw_location, display_name):
        return None, None, None
    # The visitor sees the reviewed wording itself, without internal labels.
    return raw_location, raw_location, "ornament_spatial_mapping_v1"


def plan_stop_program(
    node_id: str,
    budget_seconds: int,
    interests: list[str] | tuple[str, ...] | None = None,
    detail_level: str = "standard",
    guidance_policy: GuidancePolicy | dict[str, Any] | None = None,
) -> StopProgram:
    """Build an auditable one-to-three-item program for one reviewed stop."""
    if not isinstance(budget_seconds, int) or budget_seconds <= 0:
        raise GuideProgramError("budget_seconds 必须为大于 0 的整数")
    if detail_level not in VALID_DETAIL_LEVELS:
        raise GuideProgramError("detail_level 必须为 short、standard 或 deep")
    policy = _coerce_guidance_policy(guidance_policy)
    allocation_detail = (
        POLICY_LENGTH_TO_DETAIL[policy.explanation_length]
        if policy is not None else detail_level
    )
    card = load_guide_cards().get(node_id)
    if card is None:
        raise GuideProgramError("该点位没有可用的讲解内容")
    point_profile = point_knowledge_profile(node_id)
    excluded_objects = set(point_profile.excluded_objects if point_profile else ())
    candidates = [
        item for item in card.get("ornaments", [])
        if (
            item.get("ornament_id")
            and item.get("name")
            and item.get("craft")
            and item.get("name") not in excluded_objects
        )
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
            unallocated_content_seconds=budget_seconds,
            status="no_reviewed_candidates",
            guidance_policy=policy.to_dict() if policy else None,
        )

    count = _target_count(budget_seconds, allocation_detail, len(candidates))
    if policy is not None:
        # C7's only policy effect on selection count: it narrows, never
        # expands, what B1/B2's reviewed candidates and stop budget allow.
        count = min(count, policy.max_items_per_stop)
    selected = _select_diverse_candidates(candidates, normalised_interests, count)
    allocated_seconds = _allocate_item_seconds(budget_seconds, allocation_detail, len(selected))
    items = []
    for index, item in enumerate(selected):
        raw_location, observation_location, location_source = _location_metadata(
            item, node_id, card.get("display_name", node_id)
        )
        items.append(
            SelectedItem(
                ornament_id=item["ornament_id"],
                name=item["name"],
                craft=item["craft"],
                role=_role(index, budget_seconds, selected),
                planned_seconds=allocated_seconds[index],
                selection_reason=_selection_reason(item, normalised_interests, index),
                rag_query_hints=_rag_hints(card, item),
                raw_location=raw_location,
                observation_location=observation_location,
                location_source=location_source,
                comparison_reason=_comparison_reason(index, selected),
            )
        )
    items = tuple(items)
    used = sum(item.planned_seconds for item in items)
    return StopProgram(
        node_id=node_id,
        display_name=card.get("display_name", node_id),
        budget_seconds=budget_seconds,
        interests=normalised_interests,
        detail_level=detail_level,
        selected_items=items,
        candidate_count=len(candidates),
        allocated_content_seconds=used,
        unallocated_content_seconds=budget_seconds - used,
        selection_strategy=(
            "c7_policy_relevance_diversity_budget"
            if policy is not None else "b2_relevance_diversity_budget"
        ),
        status="brief_overview" if budget_seconds <= STOP_PROGRAM_POLICY["budget"]["brief_overview_max_seconds"] else "ready",
        guidance_policy=policy.to_dict() if policy else None,
    )
