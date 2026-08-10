"""Thin, visitor-safe adapter between the Streamlit demo and the public Agent API."""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


PUBLIC_ERROR_MESSAGE = "导览服务暂时繁忙，请稍后重试。当前会话信息不会因此自动推进。"
_UNSAFE_OUTPUT = re.compile(
    r"(?:traceback|source_ids\s*=|node_id\s*=|route_id\s*=|ornament_id\s*=|"
    r"deepseek_api_key|langsmith|c:\\|/data/|https?://)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ItinerarySummary:
    current_stop: str = "等待路线确认"
    next_stop: str = "将在路线生成后显示"
    completed_count: int = 0
    total_count: int = 0
    remaining_count: int = 0


@dataclass(frozen=True)
class DemoReply:
    text: str
    itinerary: ItinerarySummary
    is_error: bool = False
    messages: tuple[str, ...] = ()


def new_thread_id() -> str:
    return f"streamlit-demo-{uuid.uuid4()}"


def _load_stop_names() -> dict[str, str]:
    catalog = Path(__file__).resolve().parents[1] / "data" / "chen_clan_academy" / "routes" / "route_stop_catalog_v1.csv"
    if not catalog.exists():
        return {}
    with catalog.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row.get("node_id", ""): row.get("stop_name", "")
            for row in csv.DictReader(handle)
            if row.get("node_id") and row.get("stop_name")
        }


def read_public_state(thread_id: str) -> Mapping[str, Any] | None:
    """Read the post-call checkpoint only for a public itinerary summary; never mutate it."""
    try:
        import agent_graph

        snapshot = agent_graph.agent_graph.get_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        return snapshot.values if snapshot else None
    except Exception:
        return None


class DemoAdapter:
    def __init__(
        self,
        agent_call: Callable[[str, str], object],
        *,
        state_reader: Callable[[str], Mapping[str, Any] | None] = read_public_state,
        max_turns: int = 20,
        max_input_chars: int = 200,
        stop_names: Mapping[str, str] | None = None,
    ) -> None:
        self.agent_call = agent_call
        self.state_reader = state_reader
        self.max_turns = max_turns
        self.max_input_chars = max_input_chars
        self.stop_names = dict(stop_names or _load_stop_names())
        self.thread_id = new_thread_id()
        self.turn_count = 0
        self.itinerary = ItinerarySummary()

    def reset(self) -> None:
        self.thread_id = new_thread_id()
        self.turn_count = 0
        self.itinerary = ItinerarySummary()

    def send(self, user_text: str) -> DemoReply:
        text = (user_text or "").strip()
        if not text:
            return DemoReply("请输入想对导游说的话。", self.itinerary, True)
        if len(text) > self.max_input_chars:
            return DemoReply(f"单次输入请控制在 {self.max_input_chars} 字以内。", self.itinerary, True)
        if self.turn_count >= self.max_turns:
            return DemoReply("本次演示会话已达到 20 轮，请重置会话后继续体验。", self.itinerary, True)
        try:
            response = self.agent_call(text, self.thread_id)
        except Exception:
            return DemoReply(
                PUBLIC_ERROR_MESSAGE,
                self.itinerary,
                True,
                (PUBLIC_ERROR_MESSAGE,),
            )
        self.turn_count += 1
        if isinstance(response, str):
            raw_messages = (response,)
        elif isinstance(response, (list, tuple)):
            raw_messages = tuple(response)
        else:
            raw_messages = ()
        messages = tuple(
            item.strip()
            for item in raw_messages
            if isinstance(item, str) and item.strip() and not _UNSAFE_OUTPUT.search(item)
        )
        if not messages or len(messages) != len(raw_messages):
            return DemoReply(
                PUBLIC_ERROR_MESSAGE,
                self.itinerary,
                True,
                (PUBLIC_ERROR_MESSAGE,),
            )
        state = self.state_reader(self.thread_id)
        self.itinerary = self._itinerary_from_state(state)
        return DemoReply(messages[-1], self.itinerary, messages=messages)

    def _display_name(self, stop_id: object) -> str:
        if not isinstance(stop_id, str) or not stop_id:
            return "未确认"
        return self.stop_names.get(stop_id, "未确认")

    def _itinerary_from_state(self, state: Mapping[str, Any] | None) -> ItinerarySummary:
        if not isinstance(state, Mapping):
            return self.itinerary
        tour = state.get("tour_state")
        if not isinstance(tour, Mapping):
            return self.itinerary
        visited = list(tour.get("visited_stop_ids") or [])
        remaining = list(tour.get("remaining_stop_ids") or [])
        current = tour.get("current_stop_id")
        total = len(visited) + len(remaining)
        if current and current not in visited and current not in remaining:
            total += 1
        return ItinerarySummary(
            current_stop=self._display_name(current),
            next_stop=self._display_name(remaining[0]) if remaining else "路线已接近完成",
            completed_count=len(visited),
            total_count=total,
            remaining_count=len(remaining),
        )
