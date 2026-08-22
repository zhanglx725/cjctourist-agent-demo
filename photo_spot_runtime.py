"""D6 deterministic rendering for D5 editorial photo candidates.

This module never changes a route, TourState, VisitorProfile, or StopProgram.
It also never exposes an experience asset through a generic knowledge query.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from photo_spot_validation import EDITORIAL_ON_SITE_DISCLAIMER, query_available_photo_spots, validate_photo_spot_cards
from visit_safety_rules import answer_visit_safety_question, is_visit_safety_question


PHOTO_CUES = (
    "拍照", "拍一张", "拍", "怎么拍", "打卡", "机位", "构图", "合影", "自拍",
    "拍哪里", "值得拍", "拍摄建议", "拍照姿势", "摆什么姿势", "什么姿势",
    "怎么摆", "怎么站", "摆动作", "手怎么放",
)
ROUTE_CHANGE_CUES = ("加入路线", "加入行程", "加入游览", "改路线", "调整路线")
DEICTIC_CUES = ("这里", "此处", "眼前", "当前点", "当前站", "本点")
FAMILY_CUES = ("一家人", "亲子", "全家", "家庭")
SOLO_CUES = ("一个人", "自己拍", "独自", "单人")
PROTECTED_FEATURE_CUES = ("栏杆", "栏板", "石狮", "文物", "构件", "围挡", "展品")
PHOTO_SAFETY_SAFE = "safe"
PHOTO_SAFETY_UNSAFE = "unsafe"
PHOTO_SAFETY_CLARIFY = "clarify"
_PROTECTED_PATTERN = r"(?:栏杆|栏板|石狮|文物|构件|围挡|展品)"
_MOUNT_ACTION_PATTERN = r"(?:坐|骑|站|踩|爬|攀爬|攀登|趴)"
_CONTACT_ACTION_PATTERN = r"(?:倚靠|倚着|倚在|靠着|靠在|靠到)"
_CROSS_ACTION_PATTERN = r"(?:翻越|翻过|跨越|跨过)"
_EXPLICIT_UNSAFE_PHOTO_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        # 动作在前且明确落在受保护物表面：坐栏杆上、站到栏板上、爬到石狮顶部。
        rf"(?:坐|站|踩|爬|攀爬|攀登|趴)(?:在|到|上|着|于)?(?:这|那|这个|那个)?{_PROTECTED_PATTERN}(?:的)?(?:上|上面|上边|顶部|顶上|表面)",
        # “爬上石狮 / 坐上栏杆”把表面关系写在动作后、对象前。
        rf"(?:坐|站|踩|爬|攀爬|攀登|趴)(?:上|到)(?:这|那|这个|那个)?{_PROTECTED_PATTERN}",
        # 省略方位词时，坐/踩/爬等动作仍与保护对象直接成支撑关系；
        # “在栏杆旁边”由后面的方位否定排除，避免误伤安全站位。
        rf"(?:坐|骑|踩|爬|攀爬|攀登|趴)(?:在|着|于)?(?:这|那|这个|那个)?{_PROTECTED_PATTERN}(?!旁边|旁|附近|前面|后面|一侧)",
        # “骑”本身已经表达跨坐关系：骑在栏杆、骑石狮。
        rf"骑(?:在|到|上|着|于)?(?:这|那|这个|那个)?{_PROTECTED_PATTERN}",
        # 对象在前：栏杆上坐着、石狮上爬、构件顶部站着。
        rf"{_PROTECTED_PATTERN}(?:的)?(?:上|上面|上边|顶部|顶上|表面){_MOUNT_ACTION_PATTERN}",
        # 接触和跨越关系本身已经足够明确。
        rf"{_CONTACT_ACTION_PATTERN}(?:这|那|这个|那个)?{_PROTECTED_PATTERN}",
        rf"{_CROSS_ACTION_PATTERN}(?:这|那|这个|那个)?{_PROTECTED_PATTERN}",
        rf"{_PROTECTED_PATTERN}(?:能|可以|想|要|打算|准备)?(?:直接)?(?:翻|跨)(?:过|过去|越过)",
    )
)
_DEICTIC_HIGH_RISK_PATTERN = re.compile(
    r"(?:坐|骑|站|踩|爬|趴)上去|(?:翻|跨|爬)过去|(?:倚|靠)上去"
)
MARKERS_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")


def is_explicit_photo_request(user_query: str) -> bool:
    return any(cue in user_query for cue in PHOTO_CUES)


def has_photo_route_conflict(user_query: str) -> bool:
    return is_explicit_photo_request(user_query) and any(cue in user_query for cue in ROUTE_CHANGE_CUES)


def classify_photo_safety_intent(user_query: str) -> str:
    """Classify photo conduct before any point or candidate lookup.

    The matcher models the relation between an action and a protected object,
    so ordinary requests to photograph a railing are not treated as attempts
    to sit or climb on it.  High-risk deictic wording without a resolved object
    is never allowed to fall through to a recommendation.
    """
    if not is_explicit_photo_request(user_query):
        return PHOTO_SAFETY_SAFE
    compact = re.sub(r"[\s，。！？、；：,.!?;:]", "", user_query)
    if is_visit_safety_question(compact):
        return PHOTO_SAFETY_UNSAFE
    if any(pattern.search(compact) for pattern in _EXPLICIT_UNSAFE_PHOTO_PATTERNS):
        return PHOTO_SAFETY_UNSAFE
    has_protected_object = any(cue in compact for cue in PROTECTED_FEATURE_CUES)
    has_risky_action = bool(re.search(r"坐|骑|站|踩|爬|攀|趴|倚|靠|翻|跨", compact))
    explicit_safe_proximity = bool(
        re.search(rf"{_PROTECTED_PATTERN}(?:的)?(?:旁边|旁|附近|前面|后面|一侧)", compact)
        or re.search(rf"(?:旁边|旁|附近|前面|后面|一侧)(?:的)?{_PROTECTED_PATTERN}", compact)
    )
    if _DEICTIC_HIGH_RISK_PATTERN.search(compact) or (
        has_protected_object and has_risky_action and not explicit_safe_proximity
    ):
        return PHOTO_SAFETY_CLARIFY
    return PHOTO_SAFETY_SAFE


def is_unsafe_photo_request(user_query: str) -> bool:
    """Return whether a photo request violates a reviewed safety boundary.

    Contact actions still require a protected feature, so ordinary wording
    such as ``踩点拍照`` is not rejected.  Reviewed equipment and conduct
    restrictions (for example drone or flash use) are independently sufficient
    and are checked before any editorial candidate lookup.
    """
    return classify_photo_safety_intent(user_query) == PHOTO_SAFETY_UNSAFE


def _photo_safety_refusal_message() -> str:
    return (
        "不建议踩、爬、坐上、倚靠或翻越栏杆、构件、围挡和文物拍照。"
        "请留在允许停留的平地和开放区域，在不触摸构件、不阻碍通行的前提下远观取景。"
    )


def _photo_safety_clarification_message() -> str:
    return (
        "如果您的意思是坐、站、踩、爬、倚靠或跨越栏杆、构件、围挡和文物拍照，"
        "请不要这样做。请留在允许停留的平地和开放区域取景；"
        "如果您只是想拍摄它本身，可以告诉我您现在的位置。"
    )


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
        "当前没有可直接采用的点位拍摄方案。您可以在允许拍摄且不影响通行的位置远观取景，"
        "不要触摸、倚靠、攀爬或跨越构件与围挡，也不要使用受限制的设备。"
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
    lines = [f"可以参考{spot.get('title_zh') or '这一处'}取景。", _focus_text(spot.get("themes", []))]
    if poses:
        pose = poses[0]
        instruction = pose.get("instruction_zh")
        if instruction:
            lines.append(f"如现场允许，可采用较自然的方式：{instruction}")
    disclosed_field_review = False
    for limitation in selection.get("limitations", []):
        limitation = str(limitation or "").strip()
        if limitation == EDITORIAL_ON_SITE_DISCLAIMER:
            limitation = "实际可见性、光线、客流和开放情况请以现场为准。"
        # Editorial lifecycle values are internal audit metadata, not useful
        # visitor prose.  Keep the actual on-site uncertainty while hiding the
        # YAML status token and review workflow wording.
        if (
            "draft_manual_review" in limitation
            or limitation.startswith("原卡为")
            or any(marker in limitation for marker in (
                "未核验", "未审核", "审核对象", "对象 ID", "对象ID",
            ))
        ):
            disclosed_field_review = True
            continue
        if limitation and limitation not in lines:
            lines.append(limitation)
    if disclosed_field_review:
        lines.append("具体站位、可见性和现场拍摄条件仍请以现场管理要求为准。")
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
    # This check is intentionally before every D5 validation, selection, and
    # rendering call.  A dangerous action is never eligible for a candidate,
    # pose, route suggestion, or other photo guidance.
    safety_answer = answer_visit_safety_question(user_query)
    if is_explicit_photo_request(user_query) and safety_answer is not None:
        return {
            "message": safety_answer["message"],
            "mode": "photo_safety_restriction",
            "photo_spots": [],
            "point_context": point_context,
        }
    safety_intent = classify_photo_safety_intent(user_query)
    if safety_intent == PHOTO_SAFETY_UNSAFE:
        return {
            "message": _photo_safety_refusal_message(),
            "mode": "photo_safety_refusal",
            "photo_spots": [],
            "point_context": point_context,
        }
    if safety_intent == PHOTO_SAFETY_CLARIFY:
        return {
            "message": _photo_safety_clarification_message(),
            "mode": "photo_safety_clarification",
            "photo_spots": [],
            "point_context": point_context,
        }
    if has_photo_route_conflict(user_query):
        return {
        "message": "拍照/打卡建议与修改路线需要分别确认。本次不会自动把打卡点加入路线；您可以先说明想了解哪个点位的拍照/打卡建议。",
            "mode": "photo_clarification", "photo_spots": [], "point_context": point_context,
        }
    is_deictic = any(cue in user_query for cue in DEICTIC_CUES)
    if is_deictic and not point_context:
        return {
            "message": "请先告诉我您现在位于地图上的哪个点位；我不会根据聊天语气猜测拍摄位置。",
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
    if current_node_id:
        # A current or explicitly resolved point is authoritative. Never
        # answer "这里怎么拍" with candidates from other route stops.
        try:
            current_selection = query_selector(
                node_id=current_node_id,
                audience_mode=(visitor_profile or {}).get("audience_mode"),
                themes=tuple(requested_themes),
            )
            if not current_selection.get("available"):
                current_selection = query_selector(
                    node_id=current_node_id,
                    audience_mode=(visitor_profile or {}).get("audience_mode"),
                    themes=(),
                )
        except Exception:
            current_selection = {"available": False}
        if current_selection.get("available"):
            rendered_current = _render_candidate(current_selection)
            return {
                "message": "可以参考这一处拍照/打卡位置建议：\n\n" + rendered_current["message"],
                "mode": "photo_recommendation",
                "photo_spots": [rendered_current],
                "point_context": point_context,
            }
        return {
            "message": (
                "当前点位暂无可直接采用的拍照/打卡建议。我可以先提供一般安全原则："
                "请在允许拍摄且不影响通行的位置取景，不触摸、倚靠或攀坐文物与建筑构件，"
                "并遵守现场标识和工作人员要求。"
            ),
            "mode": "photo_no_current_candidate",
            "photo_spots": [],
            "point_context": point_context,
        }
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
                "message": f"当前点位暂无可直接采用的拍照/打卡建议。{_safe_generic_message()}",
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
    heading = "可以参考这些拍照/打卡位置：" if len(rendered) > 1 else "可以参考这一处拍照/打卡位置："
    # A deictic request is about the visitor's actual current position.  If
    # that position has no eligible candidate, say so explicitly before
    # offering a later route stop; otherwise the fallback can look like an
    # unsupported claim about the place the visitor is standing in.
    current_prefix = ""
    if is_deictic and current_node_id and not any(item["node_id"] == current_node_id for item in rendered):
        current_prefix = "当前点位暂没有可直接采用的拍照/打卡建议；以下是路线中可以继续参考的位置。\n\n"
    message = current_prefix + heading + "\n\n" + "\n\n".join(item["message"] for item in rendered)
    return {"message": message, "mode": "photo_recommendation", "photo_spots": rendered, "point_context": point_context}
