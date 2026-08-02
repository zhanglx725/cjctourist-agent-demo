"""Pure, deterministic text recognition for the A1 guided-tour protocol.

The classifier never changes TourState and never calls an LLM.  It converts
only high-confidence, single-purpose visitor wording into contract-whitelisted
event suggestions; ambiguity is returned as a clarification decision.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from duration_parser import has_remaining_duration_context, has_route_duration_context, parse_duration_minutes
from arrival_control import is_safe_arrival_report_text, looks_like_arrival_control
from tour_interaction import EVENTS


NODES_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")
VALID_ROUTE_KINDS = {
    "tour_event", "route_request", "replan_request", "rag_question",
    "clarification", "other",
}
NODE_ALIASES = {
    # The marker inventory explains that these two public names identify the
    # same reviewed space.  Keeping aliases here prevents an LLM guess.
    "后进中厅": ("label_rear_main_hall",),
}

# Visitor wording is normalized only for contract-whitelisted actions.  These
# are not place aliases and never create a node ID: the pending-stop guard
# below still decides whether a generic arrival is safe to execute.
BARE_ARRIVAL_SYNONYMS = frozenset(
    {
        "到了",
        "到啦",
        "到咯",
        "我到了",
        "我到啦",
        "我到咯",
        "我已到了",
        "我已经到了",
        "我到这了",
        "我到这儿了",
    }
)

# This is intentionally a narrow, controlled phrase set.  It does not make
# arbitrary multi-intent turns partially executable: only a reviewed location
# plus an explicit request to adjust the *remaining* itinerary may use it.
REMAINING_REPLAN_PHRASES = (
    "重新安排后续行程", "重新安排后面的行程", "重新安排剩余行程",
    "重新安排后面的路线",
    "调整剩余路线", "调整后续路线", "从这里重新安排后面的行程",
    "从这里安排后面的路线", "从这个点调整剩余路线", "后面从这里开始重新规划",
    "从这里重新规划后续路线", "重新安排路线",
    "从这里规划路线", "帮我重排路线", "重排路线", "从这里重新安排",
)
RESET_ROUTE_PHRASES = ("从头重新规划", "从头给我规划", "放弃现在的行程", "重新开始")
PENDING_CONFIRM_WORDS = frozenset({"确认", "确定", "可以", "好的", "好", "就这样", "用这条", "使用新路线", "确认使用", "按这个走", "按这条路线走"})

# P1-12C4 keeps these navigation controls bounded to the existing A1
# ``next_stop`` event.  They do not name a stop, route, or walking path.
NEXT_STOP_CONTROL_PHRASES = (
    "下一站怎么走", "怎么去下一站", "下一站怎么去", "下一站如何去",
    "下一站去哪", "下一站去哪儿",
    "下一个", "下一处", "下一个点", "接下来去哪", "接着去哪",
    "往下走吧", "继续去后面一站", "带我去下一站", "咱们接着往后看吧",
    "下面该去哪儿了", "然后去哪", "继续走", "往哪走",
)


@dataclass(frozen=True)
class TourIntentDecision:
    route_kind: str
    event_type: str | None = None
    arguments: dict[str, Any] | None = None
    confidence: str = "none"
    reason_code: str = "other"
    requires_clarification: bool = False
    clarification_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeResolution:
    node_id: str | None
    candidate_node_ids: tuple[str, ...]
    reason_code: str


def _load_node_names(nodes_file: Path = NODES_FILE) -> dict[str, tuple[str, ...]]:
    """Return reviewed Chinese names mapped to one or more stable node IDs."""
    grouped: dict[str, list[str]] = {}
    with nodes_file.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            node_id = (row.get("node_id") or "").strip()
            if name and node_id:
                grouped.setdefault(name, []).append(node_id)
    for alias, ids in NODE_ALIASES.items():
        grouped[alias] = list(ids)
    return {name: tuple(ids) for name, ids in grouped.items()}


def resolve_reviewed_node(user_text: str) -> NodeResolution:
    """Resolve one reviewed node name, refusing duplicate or multiple mentions."""
    names = _load_node_names()
    matched_names = [name for name in names if name in user_text]
    if not matched_names:
        return NodeResolution(None, (), "node_not_mentioned")
    # Suppress a short parent name embedded in a longer explicit mention, e.g.
    # “前院” inside “前院中部”.  Distinct names still remain ambiguous.
    maximal_names = [
        name for name in matched_names
        if not any(name != other and name in other for other in matched_names)
    ]
    if len(maximal_names) != 1:
        candidates = tuple(sorted({node_id for name in maximal_names for node_id in names[name]}))
        return NodeResolution(None, candidates, "multiple_node_mentions")
    candidates = names[maximal_names[0]]
    if len(candidates) != 1:
        return NodeResolution(None, candidates, "ambiguous_node_name")
    return NodeResolution(candidates[0], candidates, "reviewed_node_name")


def _decision(
    route_kind: str,
    *,
    event_type: str | None = None,
    arguments: dict[str, Any] | None = None,
    confidence: str = "none",
    reason_code: str,
    requires_clarification: bool = False,
    clarification_message: str | None = None,
) -> TourIntentDecision:
    if route_kind not in VALID_ROUTE_KINDS:
        raise ValueError(f"未知 route_kind：{route_kind}")
    return TourIntentDecision(
        route_kind=route_kind,
        event_type=event_type,
        arguments=arguments or {},
        confidence=confidence,
        reason_code=reason_code,
        requires_clarification=requires_clarification,
        clarification_message=clarification_message,
    )


def clarification(reason_code: str, message: str) -> TourIntentDecision:
    return _decision(
        "clarification",
        reason_code=reason_code,
        requires_clarification=True,
        clarification_message=message,
    )


def validate_event_suggestion(
    event_type: str | None, arguments: dict[str, Any] | None = None
) -> TourIntentDecision:
    """Validate any future model/recognizer suggestion against the frozen schema.

    A1-2 itself uses deterministic rules, but this validator is deliberately
    reusable if a future optional LLM synonym recognizer is introduced.
    """
    arguments = dict(arguments or {})
    if event_type not in EVENTS:
        return clarification("invalid_event_suggestion", "无法确认该导游操作，请换一种明确说法。")
    if event_type in {"arrive_at_stop"}:
        node_id = arguments.get("node_id")
        known_ids = {node_id for ids in _load_node_names().values() for node_id in ids}
        if node_id not in known_ids:
            return clarification("invalid_node_suggestion", "该点位不在已审核空间节点表中，请说出地图上的明确名称。")
    if event_type == "replan_time":
        minutes = arguments.get("available_minutes")
        if not isinstance(minutes, int) or minutes <= 0:
            return clarification("invalid_minutes_suggestion", "请告诉我明确的剩余分钟数，例如“只剩 20 分钟”。")
    if event_type == "skip_stop" and "node_id" in arguments:
        node_id = arguments["node_id"]
        known_ids = {node_id for ids in _load_node_names().values() for node_id in ids}
        if node_id not in known_ids:
            return clarification("invalid_node_suggestion", "该点位不在已审核空间节点表中，请说出地图上的明确名称。")
    return _decision(
        "tour_event",
        event_type=event_type,
        arguments=arguments,
        confidence="high",
        reason_code="validated_event_suggestion",
    )


def _has_arrival_language(text: str) -> bool:
    # A bare “到了” is a common completion of the prior navigation prompt.
    # Treat it as arrival only when it is the entire turn; longer phrases still
    # pass through the existing explicit-location and multi-intent guards.
    compact = text.strip().rstrip("。！!？?")
    if compact in BARE_ARRIVAL_SYNONYMS:
        return True
    if not looks_like_arrival_control(text):
        return False
    # “我在某处” describes location context; it does not assert a new arrival.
    # Only explicit motion/completion wording may enter the state-writing path.
    return bool(
        re.search(
            r"(?:我\s*(?:人\s*)?(?:自己\s*)?(?:(?:走|逛|晃悠)\s*)?(?:已|已经|刚|终于)?\s*(?:到|到了|抵达|到达|来到)(?:了)?|"
            r"我们\s*(?:(?:走|逛|晃悠)\s*)?(?:已|已经|刚|终于)?\s*(?:到|到了|抵达|到达|来到)(?:了)?|"
            r"(?:已|已经|刚|终于)\s*(?:(?:走|逛|晃悠)\s*)?(?:到|到了|抵达|到达|来到)(?:了)?)",
            text,
        )
        # “我在月台能看到什么” remains a static question (P1-18).  These
        # two anchored forms are the newly approved explicit physical-location
        # reports for P1-11 route-deviation handling.
        or re.match(r"^(?:我现在在|现在人在)\s*[^？?。！!]+$", text.strip())
    )


def _has_destination_language(text: str) -> bool:
    return bool(re.search(r"(?:想去|想要去|要去|准备去|打算去|接下来去(?!哪|哪儿|哪里)|带我到|准备前往)", text))


def _remaining_minutes(text: str) -> int | None:
    parsed = parse_duration_minutes(text)
    return parsed.minutes if parsed.ok and has_remaining_duration_context(text) else None


def _looks_like_route_request(text: str) -> bool:
    route_terms = ("路线", "规划", "怎么逛", "游览", "参观顺序", "导览", "带我逛")
    return any(term in text for term in route_terms) or has_route_duration_context(text)


def _looks_like_question(text: str) -> bool:
    return (
        "？" in text
        or "?" in text
        or any(
            term in text
            for term in (
                "什么",
                "为什么",
                "有什么",
                "谁",
                "哪里",
                "在哪",
                "哪年",
                "哪一年",
                "何时",
                "几点",
                "多久",
                "多少年",
                "介绍",
                "怎么走",
                "如何",
                "特点",
                "讲讲",
            )
        )
    )


def _has_factual_follow_up(text: str) -> bool:
    """Detect content requests when a control event is also present.

    A question mark by itself is normal for “下一站去哪？”, so it must not
    turn a single navigation event into a false multi-intent request.
    """
    # "下一站怎么走" and "怎么去下一站" are deterministic navigation
    # controls, not a control-plus-factual-question combination.  Keep the
    # general "怎么走" cue below for questions such as "月台怎么走".
    factual_next_stop_cues = ("什么", "为什么", "有什么", "多久", "多长", "安排", "特点", "木雕", "灰塑")
    if _is_next_stop_navigation_phrase(text) and not any(cue in text for cue in factual_next_stop_cues):
        return False
    return any(term in text for term in ("什么", "为什么", "有什么", "介绍", "怎么走", "如何", "特点", "讲讲", "多久", "多长", "安排"))


def _is_next_stop_navigation_phrase(text: str) -> bool:
    """Return whether text explicitly asks how to reach the formal next stop."""
    return any(phrase in text for phrase in NEXT_STOP_CONTROL_PHRASES)


def is_unresolved_navigation_control(text: str) -> bool:
    """Catch control-shaped but unapproved navigation wording before LLM/RAG."""
    compact = text.strip().rstrip("。！!？?")
    return bool(re.fullmatch(r"(?:接下来|接着)?(?:带路|继续走|往哪(?:儿)?走|往前走)", compact))


def _is_explicit_completion_confirmation(text: str) -> bool:
    """Recognize an imperative confirmation without executing a question."""
    if not any(phrase in text for phrase in ("确认完成本点", "确认本点完成", "确认已完成本点")):
        return False
    return not bool(re.search(r"(?:吗|么|？|\?)\s*$", text))


def _pending_arrival_fallback(
    tour_state: dict[str, Any] | None,
    interaction_state: dict[str, Any] | None,
) -> str | None:
    """Return the sole formal pending stop for an otherwise unnamed arrival.

    This is intentionally narrow: a generic "我到了" is safe only while an
    unfinished route is awaiting arrival at its one stored pending stop.  Named
    ambiguous or unknown locations continue through their clarification paths.
    """
    if not tour_state or not interaction_state:
        return None
    pending = interaction_state.get("pending_stop_id")
    if (
        interaction_state.get("stop_phase") != "navigating"
        or tour_state.get("route_status") == "completed"
        or not pending
        or pending not in tour_state.get("remaining_stop_ids", [])
    ):
        return None
    return str(pending)


def _is_generic_arrival_phrase(text: str) -> bool:
    """Return whether arrival wording contains no named or unknown destination."""
    compact = text.strip().rstrip("。！!？?")
    if compact in BARE_ARRIVAL_SYNONYMS:
        return True
    # P1-12C1 approved generalized arrival reports.  They name no destination,
    # so they may bind only the one formal pending stop after the surrounding
    # active-route guard in ``_pending_arrival_fallback`` succeeds.
    if compact in {
        "我已经走到这一站跟前了",
        "我人已经到这儿了",
        "刚刚走到该看的地方",
        "我已经到目的地了",
        "人已经到位了",
        "我们走到了",
        "我已经抵达这里了",
        "我人到了",
        "我终于抵达啦",
        "终于走到了",
        "已经来到这一站了",
        "我们走到跟前了",
    }:
        return True
    return bool(re.fullmatch(
        r"(?:我\s*)?(?:(?:已|已经|刚)\s*)?(?:到了|到达了?|到)\s*[。！!？?]?",
        text.strip(),
    ))


def is_remaining_route_replan_request(text: str) -> bool:
    """Return whether text expressly asks to adjust a live route remainder."""
    return any(phrase in text for phrase in REMAINING_REPLAN_PHRASES)


def _has_explicit_replan_origin_claim(text: str) -> bool:
    """Return whether the visitor asserts a present/reached replan origin.

    This is only used while the same turn already asks to replan.  It has no
    node-resolution power and therefore cannot turn an unreviewed phrase into
    a location fact.
    """
    return bool(re.search(
        r"(?:我\s*(?:自己\s*)?(?:(?:走|逛|晃悠)\s*)?(?:已|已经|刚)?\s*(?:到|到了)|"
        r"(?:已|已经|刚)?到达(?:了)?|我来到了|我(?:现在)?在|现在人在)",
        text,
    ))


def is_unresolved_replan_origin_request(text: str) -> bool:
    """Identify an explicitly unknown location used as a route origin.

    The guard is intentionally narrower than ordinary route planning: it
    requires a visitor-declared, unlabelled location together with a request
    to adjust the remainder.  It prevents a default-entry route from being
    created when the stated origin cannot be audited.
    """
    unknown_origin_cues = (
        "没标名字", "没有标名字", "不知道名字", "没有标识", "没标识", "无标识",
    )
    replan_cues = (
        *REMAINING_REPLAN_PHRASES,
        "后面怎么走", "后续怎么走",
    )
    return any(cue in text for cue in unknown_origin_cues) and any(
        cue in text for cue in replan_cues
    )


def is_explicit_route_reset_request(text: str) -> bool:
    """Return whether text explicitly asks to abandon the current itinerary."""
    return any(phrase in text for phrase in RESET_ROUTE_PHRASES)


def _active_tour(tour_state: dict[str, Any] | None) -> bool:
    return bool(tour_state and tour_state.get("route_status") not in {None, "completed"})


def _classify_remaining_route_replan(
    text: str,
    tour_state: dict[str, Any] | None,
) -> TourIntentDecision | None:
    """Classify only the P1-11 controlled arrival-and-replan composition."""
    if is_explicit_route_reset_request(text):
        if _active_tour(tour_state):
            return clarification(
                "route_reset_requires_confirmation",
                "放弃当前行程会清除既有进度；请先明确确认是否要重置整条路线。",
            )
        return None
    if is_unresolved_replan_origin_request(text):
        return clarification(
            "unresolved_replan_origin",
            "我暂时无法确认您所在的具体审核点位，因此不能从这个位置安全重排行程。"
            "请提供现场标识上的点位名称，或从已审核点位中选择。",
        )
    if not is_remaining_route_replan_request(text):
        return None
    # This exception is deliberately smaller than generic multi-intent
    # handling.  Completion, skip, time, finish, and factual requests still
    # require an explicit separate turn rather than being partly executed.
    if any(term in text for term in (
        "我看完了", "看完", "完成本点", "跳过", "只剩", "剩余", "改成",
        "结束导览", "结束游览", "结束路线", "什么", "讲讲", "？", "?",
    )):
        return clarification("multiple_intents", "请先单独完成、跳过、调整时间或提问，再重新安排后续路线。")
    resolution = resolve_reviewed_node(text)
    explicit_origin_claim = _has_explicit_replan_origin_claim(text)
    if not _active_tour(tour_state):
        if resolution.node_id is not None:
            return clarification(
                "initial_route_origin_not_supported",
                "当前初始路线尚不支持从非入口点直接开始；请先从入口建立路线，或说明是否需要其他帮助。",
            )
        if explicit_origin_claim:
            return clarification(
                "unresolved_replan_origin",
                "我暂时无法确认您所在的具体审核点位，因此不能从这个位置安全重排行程。"
                "请提供现场标识上的点位名称，或从已审核点位中选择。",
            )
        return None
    if resolution.reason_code in {"ambiguous_node_name", "multiple_node_mentions"}:
        return clarification(resolution.reason_code, "重规划起点不唯一，请说出一个明确的审核点位。")
    explicit_arrival = _has_arrival_language(text)
    if resolution.node_id is None and explicit_origin_claim:
        return clarification(
            "unresolved_replan_origin",
            "我暂时无法确认您所在的具体审核点位，因此不能从这个位置安全重排行程。"
            "请提供现场标识上的点位名称，或从已审核点位中选择。",
        )
    node_id = resolution.node_id or tour_state.get("current_stop_id")
    if not node_id:
        return clarification(
            "replan_origin_unresolved",
            "请先说明您当前所在的审核点位，再从这里调整后续路线。",
        )
    return _decision(
        "replan_request",
        arguments={
            "node_id": str(node_id),
            "record_arrival": bool(resolution.node_id is not None and explicit_arrival),
            "replan_scope": "remaining_route",
            "requires_confirmation": True,
        },
        confidence="high",
        reason_code="active_tour_replan_from_current_location",
    )


def _event_hits(text: str) -> set[str]:
    """Find action categories before selecting one; used to reject combinations."""
    hits: set[str] = set()
    if _has_arrival_language(text):
        hits.add("arrive_at_stop")
    if any(term in text for term in ("本点讲解结束", "讲解播放结束了")):
        hits.add("explanation_finished")
    if any(term in text for term in ("讲完了", "讲完", "看完了", "看完", "参观完了", "讲解完成")) or _is_explicit_completion_confirmation(text):
        hits.add("confirm_stop_complete")
    if any(term in text for term in ("跳过", "不去")):
        hits.add("skip_stop")
    if _remaining_minutes(text) is not None:
        hits.add("replan_time")
    if "explanation_finished" not in hits and any(term in text for term in ("结束导览", "结束游览", "结束路线", "路线结束", "游览结束", "结束了")):
        hits.add("finish_tour")
    if any(term in text for term in ("再讲详细", "详细一点", "讲细一点", "展开讲解")):
        hits.add("request_stop_detail")
    # “讲完了，去下一站” is one confirmation intent, not two events.
    if "confirm_stop_complete" not in hits and _is_next_stop_navigation_phrase(text):
        hits.add("next_stop")
    return hits


def classify_tour_intent(
    user_text: str,
    tour_state: dict[str, Any] | None = None,
    interaction_state: dict[str, Any] | None = None,
) -> TourIntentDecision:
    """Classify one visitor message without changing any state.

    ``tour_state`` and ``interaction_state`` are used only to decide whether an
    omitted skip target has enough context.  They are never modified.
    """
    text = user_text.strip()
    if not text:
        return clarification("empty_input", "请告诉我您想继续游览、提问，还是规划路线。")

    compact = text.rstrip("。！!？?")
    if (
        compact in PENDING_CONFIRM_WORDS
        and interaction_state
        and interaction_state.get("stop_phase") == "awaiting_confirmation"
        and tour_state
        and tour_state.get("current_stop_id") == interaction_state.get("pending_stop_id")
    ):
        return validate_event_suggestion("confirm_stop_complete")

    parsed_duration = parse_duration_minutes(text)
    if has_remaining_duration_context(text) and parsed_duration.reason_code == "ambiguous_duration":
        return clarification("ambiguous_duration", "时间表达包含多个不同分钟数，请只确认一个剩余时间。")

    replan = _classify_remaining_route_replan(text, tour_state)
    if replan is not None:
        return replan

    hits = _event_hits(text)
    # A control action plus a factual request must not partly execute in A1-2.
    fact_cue = _has_factual_follow_up(text) and "request_stop_detail" not in hits
    if len(hits) > 1 or (hits and fact_cue):
        return clarification("multiple_intents", "我检测到多个操作或问题，请一次告诉我一个需求。")

    # A declared destination is not an arrival report.  Keep its established
    # clarification before the broader arrival-shaped safety guard so intent
    # wording is never reported as an unresolved physical location.
    if _has_destination_language(text):
        return clarification("destination_not_arrival", "这是前往意图，不会记录为已到达；如需路线请说明可用时间。")

    # Arrival is the final control guard, not a shortcut around P1-11
    # replan reasons or A1 multi-intent detection.  Its only job is to keep a
    # malformed location-control turn out of RAG once the higher-priority
    # specialist controls above have declined it.
    if looks_like_arrival_control(text) and not is_safe_arrival_report_text(text):
        return clarification(
            "arrival_not_safely_resolved",
            "我还不能安全确认您到达的具体点位。请告诉我现场点位名称，或确认是否已经到达当前路线的下一站。",
        )

    # P1-12C1: semantic normalization can propose an arrival candidate, but
    # the original wording remains the authority for whether A1 may execute
    # it.  This shared guard rejects intention, in-transit, negated,
    # hypothetical and third-party language before it can bind a reviewed node
    # or the unique pending stop.  Multi-intent handling above intentionally
    # retains its frozen clarification reason.
    if _has_arrival_language(text) and not is_safe_arrival_report_text(text):
        return clarification(
            "arrival_report_not_executable",
            "我不能据此确认您已经到达。请在到达后用明确、单一的第一人称表达说明当前位置。",
        )

    if hits:
        event = next(iter(hits))
        if event == "arrive_at_stop":
            if _has_destination_language(text):
                return clarification("destination_not_arrival", "您是想前往该点，还是已经到达？请明确告诉我。")
            resolution = resolve_reviewed_node(text)
            if resolution.node_id is None:
                if resolution.reason_code == "ambiguous_node_name":
                    return clarification("ambiguous_node_name", "该名称对应多个审核点位，请补充方位或选择具体点位。")
                if resolution.reason_code == "multiple_node_mentions":
                    return clarification("multiple_node_mentions", "您提到了多个点位，请一次确认一个当前位置。")
                pending = _pending_arrival_fallback(tour_state, interaction_state)
                if pending is not None and _is_generic_arrival_phrase(text):
                    return validate_event_suggestion("arrive_at_stop", {"node_id": pending})
                return clarification("arrival_node_unresolved", "我知道您已到达，但无法确认点位名称，请说出地图上的明确点位。")
            return validate_event_suggestion("arrive_at_stop", {"node_id": resolution.node_id})
        if event == "skip_stop":
            resolution = resolve_reviewed_node(text)
            if resolution.reason_code in {"ambiguous_node_name", "multiple_node_mentions"}:
                return clarification(resolution.reason_code, "跳过的点位不唯一，请指定一个明确点位。")
            if resolution.node_id:
                return validate_event_suggestion("skip_stop", {"node_id": resolution.node_id})
            has_context = bool(tour_state and interaction_state and interaction_state.get("pending_stop_id"))
            if not has_context:
                return clarification("skip_target_unresolved", "请先建立路线或说出要跳过的明确点位。")
            return validate_event_suggestion("skip_stop")
        if event == "replan_time":
            return validate_event_suggestion("replan_time", {"available_minutes": _remaining_minutes(text)})
        return validate_event_suggestion(event)

    if any(term in text for term in ("快一点", "快些", "赶时间")):
        return clarification("missing_remaining_minutes", "请告诉我还剩多少分钟，例如“我只剩 20 分钟”。")
    if _looks_like_route_request(text):
        return _decision("route_request", confidence="high", reason_code="explicit_route_request")
    if _looks_like_question(text):
        return _decision("rag_question", confidence="high", reason_code="factual_or_navigation_question")
    return _decision("other", reason_code="open_conversation")
