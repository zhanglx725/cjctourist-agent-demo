import unittest

from langchain_core.messages import HumanMessage

from agent_graph import extended_profile_control_node, route_initial_request
from visitor_profile import create_visitor_profile


class AgentExtendedProfileControlTests(unittest.TestCase):
    def _state(self, text, **extra):
        return {"messages": [HumanMessage(content=text)], "performance_metrics": [], **extra}

    def test_routes_explicit_control_without_llm(self):
        self.assertEqual(route_initial_request(self._state("给小朋友讲")), "extended_profile_control")
        self.assertEqual(route_initial_request(self._state("我们一起看看")), "llm_think")

    def test_control_does_not_mutate_tour_progress(self):
        tour = {"visited_stop_ids": ["a"], "skipped_stop_ids": ["b"], "route_status": "touring"}
        result = extended_profile_control_node(self._state("用故事方式讲", tour_state=tour))
        self.assertEqual(result["visitor_profile"]["explanation_style"], "story")
        self.assertNotIn("tour_state", result)
        self.assertNotIn("tour_interaction_state", result)

    def test_delete_clears_only_profile_session_data(self):
        state = self._state(
            "删除本次偏好", tour_state={"route_status": "touring", "visited_stop_ids": ["x"]},
            visitor_profile=create_visitor_profile(audience_mode="family").to_dict(),
            profile_collection={"status": "collecting"},
        )
        result = extended_profile_control_node(state)
        self.assertIsNone(result["visitor_profile"])
        self.assertIsNone(result["profile_collection"])
        self.assertNotIn("tour_state", result)


if __name__ == "__main__":
    unittest.main()
