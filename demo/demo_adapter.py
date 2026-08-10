"""Visitor-safe adapter that consumes the Agent's public turn contract only."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from agent_graph import PublicMessage, PublicTourSummary, PublicTurnResult


PUBLIC_ERROR_MESSAGE = "导览服务暂时繁忙，请稍后重试。当前会话信息不会因此自动推进。"


@dataclass(frozen=True)
class DemoReply:
    messages: tuple[PublicMessage, ...]
    itinerary: PublicTourSummary
    is_error: bool = False


def new_thread_id() -> str:
    return f"streamlit-demo-{uuid.uuid4()}"


class DemoAdapter:
    """Keeps UI-only session state; it never reads or reconstructs Graph state."""

    def __init__(
        self,
        agent_call: Callable[[str, str], PublicTurnResult],
        *,
        session_starter: Callable[[str], PublicTurnResult],
        max_turns: int = 20,
        max_input_chars: int = 200,
    ) -> None:
        self.agent_call = agent_call
        self.session_starter = session_starter
        self.max_turns = max_turns
        self.max_input_chars = max_input_chars
        self.thread_id = new_thread_id()
        self.turn_count = 0
        self.itinerary = PublicTourSummary()
        self._displayed_message_ids: set[str] = set()

    def reset(self) -> None:
        self.thread_id = new_thread_id()
        self.turn_count = 0
        self.itinerary = PublicTourSummary()
        self._displayed_message_ids.clear()

    def _error(self) -> DemoReply:
        return DemoReply(
            messages=(PublicMessage(
                message_id=f"demo-error-{self.turn_count}",
                scene_kind="system",
                text=PUBLIC_ERROR_MESSAGE,
                active_takeover=False,
            ),),
            itinerary=self.itinerary,
            is_error=True,
        )

    def start(self) -> DemoReply:
        """Fetch the Graph-owned bilingual welcome for this fresh thread."""
        try:
            response = self.session_starter(self.thread_id)
        except Exception:
            return self._error()
        if not isinstance(response, PublicTurnResult) or not response.public_messages:
            return self._error()
        fresh_messages = tuple(
            message
            for message in response.public_messages
            if message.message_id not in self._displayed_message_ids
        )
        if not fresh_messages:
            return self._error()
        self._displayed_message_ids.update(message.message_id for message in fresh_messages)
        self.itinerary = response.tour_summary
        return DemoReply(fresh_messages, self.itinerary)

    def send(self, user_text: str) -> DemoReply:
        text = (user_text or "").strip()
        if not text or len(text) > self.max_input_chars or self.turn_count >= self.max_turns:
            return self._error()
        try:
            response = self.agent_call(text, self.thread_id)
        except Exception:
            return self._error()
        self.turn_count += 1
        if not isinstance(response, PublicTurnResult):
            return self._error()
        fresh_messages = tuple(
            message
            for message in response.public_messages
            if message.message_id not in self._displayed_message_ids
        )
        if not fresh_messages:
            return self._error()
        self._displayed_message_ids.update(message.message_id for message in fresh_messages)
        self.itinerary = response.tour_summary
        return DemoReply(fresh_messages, self.itinerary)
