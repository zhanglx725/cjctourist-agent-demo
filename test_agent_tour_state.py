"""No-network tests for TourState intent routing inside the LangGraph agent."""

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    arrive_at_stop_node,
    direct_route_node,
    finish_tour_node,
    next_stop_node,
    replan_time_node,
    route_initial_request,
    skip_stop_node,
)


def _message_state(text: str, tour_state: dict | None = None) -> dict:
    state = {"messages": [HumanMessage(content=text)], "performance_metrics": []}
    if tour_state is not None:
        state["tour_state"] = tour_state
    return state


class AgentTourStateTests(unittest.TestCase):
    def test_start_route_initializes_session_tour_state(self):
        result = direct_route_node(_message_state("我有30分钟，帮我规划路线"))
        tour = result["tour_state"]
        self.assertEqual(tour["selected_route_id"], "highlights_30")
        self.assertIsNone(tour["current_stop_id"])
        self.assertEqual(tour["route_status"], "not_started")

    def test_arrival_and_next_stop_use_deterministic_nodes(self):
        tour = direct_route_node(_message_state("我有30分钟，帮我规划路线"))["tour_state"]
        self.assertEqual(route_initial_request(_message_state("我到前院中部了", tour)), "arrive_at_stop")
        arrived = arrive_at_stop_node(_message_state("我到前院中部了", tour))
        self.assertEqual(arrived["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])
        next_result = next_stop_node(_message_state("下一站去哪？", arrived["tour_state"]))
        self.assertIn("月台", next_result["messages"][0].content)

    def test_skip_and_time_replan_update_state_without_llm(self):
        tour = direct_route_node(_message_state("我有30分钟，帮我规划路线"))["tour_state"]
        arrived = arrive_at_stop_node(_message_state("我到前院中部了", tour))["tour_state"]
        self.assertEqual(route_initial_request(_message_state("跳过这里", arrived)), "skip_stop")
        skipped = skip_stop_node(_message_state("跳过这里", arrived))["tour_state"]
        self.assertIn("label_moon_platform", skipped["skipped_stop_ids"])
        self.assertEqual(route_initial_request(_message_state("只剩20分钟", skipped)), "replan_time")
        replanned = replan_time_node(_message_state("只剩20分钟", skipped))["tour_state"]
        self.assertEqual(replanned["remaining_minutes"], 20)
        self.assertNotIn("label_moon_platform", replanned["remaining_stop_ids"])

    def test_finish_tour_preserves_real_visit_counts(self):
        tour = direct_route_node(_message_state("我有30分钟，帮我规划路线"))["tour_state"]
        arrived = arrive_at_stop_node(_message_state("我到前院中部了", tour))["tour_state"]
        self.assertEqual(route_initial_request(_message_state("路线结束了", arrived)), "finish_tour")
        finished = finish_tour_node(_message_state("路线结束了", arrived))
        self.assertEqual(finished["tour_state"]["route_status"], "completed")
        self.assertIn("已完成讲解点 1 个", finished["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
