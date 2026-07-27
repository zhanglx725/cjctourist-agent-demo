"""D6 deterministic rendering for D5 editorial photo candidates.

This module never changes a route, TourState, VisitorProfile, or StopProgram.
It also never exposes an experience asset through a generic knowledge query.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from photo_spot_validation import EDITORIAL_ON_SITE_DISCLAIMER, query_available_photo_spots, validate_photo_spot_cards


PHOTO_CUES = ("拍照", "怎么拍", "打卡", "机位", "构图", "合影", "自拍", "拍哪里", "值得拍", "拍摄建议")
ROUTE_CHANGE_CUES = ("加入路线", "加入行程", "加入游览", "改路线", "调整路线")
DEICTIC_CUES = ("这里", "此处", "眼前", "当前点", "当前站", "本点")
FAMILY_CUES = ("一家人", "亲子", "全家", "家庭")
SOLO_CUES = ("一个人", "自己拍", "独自", "单人")
MARKERS_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")


def is_explicit_photo_request(user_query: str) -> bool:
    return any(cue in user_query for cue in PHOTO_CUES)


def has_photo_route_conflict(user_query: str) -> bool:
    return is_explicit_photo_request(user_query) and any(cue in user_query for cue in ROUTE_CHANGE_CUES)


def _audience_group_hints(user_query: str, visitor_profile: dict[str, Any] | None) -> set[str]:
    profile = visitor_profile or {}
    hints: set[str] = set()
    if any(cue in user_query for cue in FAMILY_CUES) or profile.get("audience_mode") == "family":
        hints.update({"family", "parents_with_children", "multigenerational", "elders"})
    if any(cue in user_query for cue in SOLO_CUES):
        hints.add("solo_travelers")
    if "合影" in user_query:
        hints.update({"friends", "couples", "family", "multigenerational"})
    return hints


def _theme_hints(user_query: str) -> set[str]:
    mapping = {
        "灰塑": "grey_plaster", "木雕": "woodcarving", "石雕": "craft_detail",
        "建筑": "architecture_signature", "工艺": "craft_detail", "三国": "three_kingdoms",
        "故事": "story_task", "一个人": "portrait_memory", "自拍": "portrait_memory",
    }
    return {theme for token, theme in mapping.items() if token in user_query}


def _focus_text(themes: list[str]) -> str:
    themes = set(themes)
    if "story_task" in themes or "three_kingdoms" in themes:
        return "可以尝试把故事题材或人物关系作为画面重点，先确认构件细节是否清楚可见。"
    if "craft_detail" in themes or "openwork" in themes:
        return "可以尝试把装饰细节与建筑构件的前后层次作为画面重点。"
    if "corridor_perspective" in themes or "framing_view" in themes:
        return "可以尝试利用廊道、门洞或建筑线条形成画面层次，但不要为构图停留在通道中。"
    if "portrait_memory" in themes:
        return "可以尝试让人物与建筑层次同框，保留到访环境，而不把文物作为摆拍道具。"
    return "可以尝试保留建筑轮廓与装饰细节的层次关系。"


def _candidate_sort_key(
    *,
    card_id: str,
    node_id: str,
    current_node_id: str | None,
    is_current_child: bool,
    target_groups: list[str] | tuple[str, ...],
    group_hints: set[str],
    remaining_rank: dict[str, int],
    themes: set[str],
    requested_themes: set[str],
) -> tuple[int, int, int, int, str]:
    """Return the auditable, deterministic D6 candidate ordering key.

    The tuple order deliberately mirrors the product rule.  A lower key is
    better: current location (or its reviewed child) first, then an explicit
    one-turn group request, then the remaining-route order, then a requested
    theme match, and finally the immutable card ID.  No dictionary order is a
    ranking signal.
    """
    if node_id == current_node_id:
        current_priority = 0
    elif is_current_child:
        current_priority = 1
    else:
        current_priority = 2
    group_priority = 0 if (group_hints and group_hints.intersection(target_groups)) else 1
    route_priority = remaining_rank.get(node_id, 999)
    theme_priority = -len(themes.intersection(requested_themes))
    return (current_priority, group_priority, route_priority, theme_priority, card_id)


def _safe_generic_message() -> str:
    return (
        "当前没有可用的项目编辑拍摄候选。我只能给出通用建议：在允许拍摄、且不影响通行的位置远观取景，"
        "不要触摸、倚靠、攀爬或跨越构件与围挡，也不要使用受限制的设备。\n\n"
        + EDITORIAL_ON_SITE_DISCLAIMER
    )


@lru_cache(maxsize=1)
def _parent_node_ids() -> dict[str, str]:
    try:
        with MARKERS_FILE.open(encoding="utf-8-sig", newline="") as handle:
            return {
                row["node_id"]: row["parent_node_id"]
                for row in csv.DictReader(handle)
                if row.get("node_id") and row.get("parent_node_id")
            }
    except OSError:
        return {}


def _render_candidate(selection: dict[str, Any]) -> dict[str, Any]:
    spot = selection["photo_spot"]
    poses = selection.get("pose_templates", [])
    lines = [f"{spot.get('title_zh') or '该点位'}可以作为一个项目编辑拍摄候选。", _focus_text(spot.get("themes", []))]
    if poses:
        pose = poses[0]
        instruction = pose.get("instruction_zh")
        if instruction:
            lines.append(f"如现场允许，可采用较自然的方式：{instruction}")
    for limitation in selection.get("limitations", []):
        if limitation and limitation not in lines:
            lines.append(str(limitation))
    return {"message": "\n".join(lines), "node_id": spot.get("node_id"), "photo_spot": spot}


def answer_photo_request(
    user_query: str,
    *,
    point_context: dict[str, Any] | None,
    tour_state: dict[str, Any] | None,
    visitor_profile: dict[str, Any] | None,
    query_selector: Callable[..., dict[str, Any]] = query_available_photo_spots,
    candidate_validator: Callable[[], dict[str, dict[str, Any]]] = validate_photo_spot_cards,
) -> dict[str, Any]:
    """Create a D6 response from D5 candidates, with no state side effects."""
    if has_photo_route_conflict(user_query):
        return {
            "message": "拍照建议与修改路线需要分别确认。本次不会自动把打卡点加入路线；您可以先说明想了解哪个点位的拍摄建议。",
            "mode": "photo_clarification", "photo_spots": [], "point_context": point_context,
        }
    is_deictic = any(cue in user_query for cue in DEICTIC_CUES)
    if is_deictic and not point_context:
        return {
            "message": "请先告诉我您现在位于哪个已审核点位；我不会根据聊天语气猜测拍摄位置。",
            "mode": "photo_location_required", "photo_spots": [], "point_context": None,
        }
    try:
        candidates = candidate_validator()
    except Exception:
        candidates = {}
    if not candidates:
        return {"message": _safe_generic_message(), "mode": "photo_unavailable", "photo_spots": [], "point_context": point_context}

    requested_themes = _theme_hints(user_query)
    group_hints = _audience_group_hints(user_query, visitor_profile)
    current_node_id = point_context.get("node_id") if point_context else None
    parent_ids = _parent_node_ids()
    remaining = list((tour_state or {}).get("remaining_stop_ids") or [])
    remaining_rank = {node_id: index for index, node_id in enumerate(remaining)}
    # Keep the approved selection that was scored.  Re-querying during
    # rendering could otherwise make a stateful/updated data provider change
    # the order after we have applied route and audience priorities.
    scored: list[tuple[tuple[int, int, int, int, str], str, dict[str, Any]]] = []
    for card_id, verdict in candidates.items():
        if not verdict.get("available"):
            continue
        node_id = verdict.get("node_id")
        # Without an actual current location, ``None == None`` must never
        # promote a root-level node into the "current child" priority tier.
        is_current_child = current_node_id is not None and parent_ids.get(node_id) == current_node_id
        # The D5 selector retains raw themes but no mixed capture wording.
        try:
            selection = query_selector(node_id=node_id, audience_mode=(visitor_profile or {}).get("audience_mode"), themes=tuple(requested_themes))
        except Exception:
            continue
        if not selection.get("available"):
            try:
                selection = query_selector(node_id=node_id, audience_mode=(visitor_profile or {}).get("audience_mode"), themes=())
            except Exception:
                continue
        if not selection.get("available"):
            continue
        spot = selection.get("photo_spot", {})
        themes = set(spot.get("themes", []))
        # Group wording is only a one-turn ranking hint; it is never persisted.
        sort_key = _candidate_sort_key(
            card_id=card_id,
            node_id=node_id,
            current_node_id=current_node_id,
            is_current_child=is_current_child,
            target_groups=tuple(spot.get("target_groups", [])),
            group_hints=group_hints,
            remaining_rank=remaining_rank,
            themes=themes,
            requested_themes=requested_themes,
        )
        scored.append((sort_key, card_id, selection))

    if not scored:
        if current_node_id:
            return {
                "message": f"当前点位暂无可用的项目编辑拍摄候选。{_safe_generic_message()}",
                "mode": "photo_no_current_candidate", "photo_spots": [], "point_context": point_context,
            }
        return {"message": _safe_generic_message(), "mode": "photo_unavailable", "photo_spots": [], "point_context": point_context}

    chosen_nodes: set[str] = set()
    rendered: list[dict[str, Any]] = []
    for _, card_id, selection in sorted(scored, key=lambda item: item[0]):
        node_id = candidates[card_id]["node_id"]
        if node_id in chosen_nodes:
            continue
        if selection.get("available"):
            rendered.append(_render_candidate(selection))
            chosen_nodes.add(node_id)
        if len(rendered) == 3:
            break
    if not rendered:
        return {"message": _safe_generic_message(), "mode": "photo_unavailable", "photo_spots": [], "point_context": point_context}
    heading = "为您整理了这些项目编辑拍摄候选：" if len(rendered) > 1 else "可以参考这一处项目编辑拍摄候选："
    # A deictic request is about the visitor's actual current position.  If
    # that position has no eligible candidate, say so explicitly before
    # offering a later route stop; otherwise the fallback can look like an
    # unsupported claim about the place the visitor is standing in.
    current_prefix = ""
    if is_deictic and current_node_id and not any(item["node_id"] == current_node_id for item in rendered):
        current_prefix = "当前点位暂没有可用的项目编辑拍摄候选；以下是路线中可继续参考的候选。\n\n"
    message = current_prefix + heading + "\n\n" + "\n\n".join(item["message"] for item in rendered)
    return {"message": message, "mode": "photo_recommendation", "photo_spots": rendered, "point_context": point_context}
