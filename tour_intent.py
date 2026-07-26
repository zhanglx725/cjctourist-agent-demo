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

from tour_interaction import EVENTS


NODES_FILE = Path("data/chen_clan_academy/spatial/marker_inventory_v0.csv")
VALID_ROUTE_KINDS = {"tour_event", "route_request", "rag_question", "clarification", "other"}
NODE_ALIASES = {
    # The marker inventory explains that these two public names identify the
    # same reviewed space.  Keeping aliases here prevents an LLM guess.
    "后进中厅": ("label_rear_main_hall",),
}


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
    return bool(re.search(r"(?:我\s*(?:已|已经|刚)?\s*(?:到|到了|在)|(?:已|已经|刚)?到达(?:了)?|我来到了)", text))


def _has_destination_language(text: str) -> bool:
    return bool(re.search(r"(?:想去|想要去|要去|去).{0,12}(?:看看|参观|逛逛|一下)", text))


def _remaining_minutes(text: str) -> int | None:
    match = re.search(r"(?:只剩|还剩|剩余)\s*(\d{1,3})\s*分钟", text)
    return int(match.group(1)) if match else None


def _looks_like_route_request(text: str) -> bool:
    route_terms = ("路线", "规划", "怎么逛", "游览", "参观顺序", "半小时", "一小时", "90分钟")
    return any(term in text for term in route_terms) or bool(re.search(r"(?:我有|有)\s*\d{1,3}\s*分钟", text))


def _looks_like_question(text: str) -> bool:
    return (
        "？" in text
        or "?" in text
        or any(term in text for term in ("什么", "为什么", "有什么", "介绍", "怎么走", "如何", "特点", "讲讲"))
    )


def _has_factual_follow_up(text: str) -> bool:
    """Detect content requests when a control event is also present.

    A question mark by itself is normal for “下一站去哪？”, so it must not
    turn a single navigation event into a false multi-intent request.
    """
    return any(term in text for term in ("什么", "为什么", "有什么", "介绍", "怎么走", "如何", "特点", "讲讲"))


def _event_hits(text: str) -> set[str]:
    """Find action categories before selecting one; used to reject combinations."""
    hits: set[str] = set()
    if _has_arrival_language(text):
        hits.add("arrive_at_stop")
    if any(term in text for term in ("讲完了", "讲完", "看完了", "看完", "参观完了", "讲解完成")):
        hits.add("confirm_stop_complete")
    if any(term in text for term in ("跳过", "不去")):
        hits.add("skip_stop")
    if _remaining_minutes(text) is not None:
        hits.add("replan_time")
    if any(term in text for term in ("结束导览", "结束游览", "结束路线", "路线结束", "游览结束", "结束了")):
        hits.add("finish_tour")
    if any(term in text for term in ("再讲详细", "详细一点", "讲细一点", "展开讲解")):
        hits.add("request_stop_detail")
    # “讲完了，去下一站” is one confirmation intent, not two events.
    if "confirm_stop_complete" not in hits and any(term in text for term in ("下一站", "接下来去哪", "然后去哪")):
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

    hits = _event_hits(text)
    # A control action plus a factual request must not partly execute in A1-2.
    fact_cue = _has_factual_follow_up(text) and "request_stop_detail" not in hits
    if len(hits) > 1 or (hits and fact_cue):
        return clarification("multiple_intents", "我检测到多个操作或问题，请一次告诉我一个需求。")

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
    if _has_destination_language(text):
        return clarification("destination_not_arrival", "这是前往意图，不会记录为已到达；如需路线请说明可用时间。")
    if _looks_like_route_request(text):
        return _decision("route_request", confidence="high", reason_code="explicit_route_request")
    if _looks_like_question(text):
        return _decision("rag_question", confidence="high", reason_code="factual_or_navigation_question")
    return _decision("other", reason_code="open_conversation")
