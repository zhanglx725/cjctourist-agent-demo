import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph


class _FakeGraph:
    def __init__(self, messages):
        self.calls = []
        self.messages = messages

    def invoke(self, state, config):
        self.calls.append((state, config))
        return {"messages": self.messages, "tour_state": {"visited_stop_ids": [], "remaining_stop_ids": []}}


def _message(message_id, text, scene_kind, **metadata):
    return AIMessage(
        id=message_id,
        content=text,
        additional_kwargs={"public_scene_kind": scene_kind, **metadata},
    )


class ChatPublicTurnTests(unittest.TestCase):
    def test_returns_only_current_explicit_public_messages_in_commit_order(self):
        graph = _FakeGraph([
            HumanMessage(content="older turn"),
            _message("old", "older reply", "route_planning"),
            HumanMessage(content="plan a route"),
            _message("route", "role route planning", "route_planning", route_role_narration=True),
            _message("opening", "role route opening", "route_opening", route_role_narration=True),
            _message("stop", "committed stop guidance", "stop_guidance", role_narration=True),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("plan a route", "public-turn-test")

        self.assertEqual([item.message_id for item in result.public_messages], ["route", "opening", "stop"])
        self.assertEqual([item.scene_kind for item in result.public_messages], ["route_planning", "route_opening", "stop_guidance"])
        self.assertTrue(result.public_messages[0].active_takeover)
        self.assertEqual(len(graph.calls), 1)

    def test_route_fallback_is_public_when_active_does_not_take_over(self):
        graph = _FakeGraph([
            HumanMessage(content="plan a route"),
            _message("route-fallback", "deterministic route", "route_planning", direct_route_plan=True),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("plan a route", "route-fallback")

        self.assertEqual(result.public_messages[0].text, "deterministic route")
        self.assertFalse(result.public_messages[0].active_takeover)

    def test_stop_guidance_fallback_remains_the_only_public_stop_message(self):
        graph = _FakeGraph([
            HumanMessage(content="arrive"),
            _message("stop-fallback", "deterministic stop guidance", "stop_guidance", stop_guidance=True),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("arrive", "stop-fallback")

        self.assertEqual(len(result.public_messages), 1)
        self.assertEqual(result.public_messages[0].scene_kind, "stop_guidance")
        self.assertFalse(result.public_messages[0].active_takeover)

    def test_unmarked_and_internal_text_are_not_public(self):
        graph = _FakeGraph([
            HumanMessage(content="arrive"),
            AIMessage(id="draft", content="role_narration_generation draft"),
            _message("unsafe", "source_ids=S1", "stop_guidance"),
            _message("safe", "final visitor guidance", "stop_guidance"),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("arrive", "safe-output")

        self.assertEqual([item.message_id for item in result.public_messages], ["safe"])

    def test_explicit_generic_public_reply_keeps_tour_events_and_questions_available(self):
        graph = _FakeGraph([
            HumanMessage(content="完成本点"),
            _message("complete", "已完成本点，请前往下一站。", "assistant"),
            _message("question", "灰塑以石灰为主要材料。", "tour_qa"),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("完成本点", "generic-public")

        self.assertEqual(
            [item.scene_kind for item in result.public_messages],
            ["assistant", "tour_qa"],
        )

    def test_contract_scene_tags_for_arrival_navigation_and_safety_are_public(self):
        graph = _FakeGraph([
            HumanMessage(content="continue"),
            _message("arrival", "你已到达前院中部，现在开始本点讲解。", "arrival_confirmation"),
            _message("navigation", "请沿中路前往下一站。", "navigation"),
            _message("safety", "不建议踩踏栏杆拍照。", "safety_refusal"),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("continue", "contract-scenes")

        self.assertEqual(
            [item.scene_kind for item in result.public_messages],
            ["arrival_confirmation", "navigation", "safety_refusal"],
        )

    def test_tour_closing_summary_and_recommendation_remain_separate_public_messages(self):
        graph = _FakeGraph([
            HumanMessage(content="结束游览"),
            _message("finish", "游览已结束。", "assistant"),
            _message("summary", "本次游览总结。", "tour_closing"),
            _message("recommendation", "是否需要附近推荐？", "tour_closing"),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.chat_public_turn("结束游览", "tour-closing")

        self.assertEqual(
            [item.message_id for item in result.public_messages],
            ["finish", "summary", "recommendation"],
        )

    def test_start_session_returns_marked_bilingual_welcome_without_a_user_message(self):
        graph = _FakeGraph([
            _message("welcome", "中文欢迎\n\nEnglish welcome", "welcome"),
        ])
        with patch.object(agent_graph, "agent_graph", graph):
            result = agent_graph.start_public_session("welcome-thread")

        self.assertEqual([item.scene_kind for item in result.public_messages], ["welcome"])
        self.assertEqual(len(graph.calls), 1)


if __name__ == "__main__":
    unittest.main()
