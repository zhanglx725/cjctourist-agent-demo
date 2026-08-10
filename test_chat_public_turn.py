import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph


class _FakeGraph:
    def __init__(self):
        self.calls = []

    def invoke(self, state, config):
        self.calls.append((state, config))
        return {
            "messages": [
                HumanMessage(content="older turn"),
                AIMessage(content="older reply"),
                HumanMessage(content="plan a route"),
                AIMessage(
                    content="legacy direct route",
                    additional_kwargs={"direct_route_plan": True},
                ),
                AIMessage(
                    content="role route planning",
                    additional_kwargs={"route_role_narration": True},
                ),
                AIMessage(
                    content="role route opening",
                    additional_kwargs={"route_role_narration": True},
                ),
                AIMessage(content="committed stop guidance"),
            ]
        }


class ChatPublicTurnTests(unittest.TestCase):
    def test_returns_current_public_messages_once_and_hides_replaced_route(self):
        graph = _FakeGraph()
        with patch.object(agent_graph, "agent_graph", graph):
            messages = agent_graph.chat_public_turn("plan a route", "public-turn-test")

        self.assertEqual(
            messages,
            ["role route planning", "role route opening", "committed stop guidance"],
        )
        self.assertEqual(len(graph.calls), 1)


if __name__ == "__main__":
    unittest.main()
