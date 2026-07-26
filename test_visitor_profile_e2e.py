"""C9 offline acceptance: profile, policy, tour snapshot and guidance agree."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    direct_route_node, extended_profile_control_node, route_initial_request,
    stop_guidance_node, tour_event_node,
)
from guidance_policy import build_guidance_policy
from tour_interaction import handle_tour_event


RAG = json.dumps({"evidence": [{
    "document": "07_ornament_crafts.md", "title_path": ["工艺", "灰塑"],
    "source_ids": ["S10"], "content": "灰塑是岭南传统建筑装饰工艺。",
}]}, ensure_ascii=False)


def state(text: str, initial: dict | None = None) -> dict:
    return {**(initial or {}), "messages": [HumanMessage(content=text)], "performance_metrics": []}


class VisitorProfileE2ETests(unittest.TestCase):
    def _started(self) -> dict:
        return direct_route_node(state("我有30分钟，喜欢灰塑，标准讲解，请规划路线"))

    def _guided(self) -> dict:
        started = self._started()
        child = extended_profile_control_node(state("给小朋友用故事方式讲", started))
        active = {**started, **child}
        arrived = tour_event_node(state("我到前院中部了", active))
        active = {**active, **arrived}
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = RAG
            guide = stop_guidance_node(active)
        return {**active, **guide}

    def test_profile_policy_snapshot_and_program_are_traceable(self):
        guided = self._guided()
        profile = guided["visitor_profile"]
        policy = build_guidance_policy(profile).to_dict()
        self.assertEqual(guided["tour_state"]["available_minutes"], profile["available_minutes"])
        self.assertEqual(guided["tour_state"]["interests"], profile["interests"])
        self.assertEqual(guided["tour_state"]["detail_level"], profile["detail_level"])
        self.assertEqual(guided["active_stop_program"]["guidance_policy"], policy)
        self.assertEqual(guided["active_stop_program"]["node_id"], "stop_front_courtyard_center")

    def test_profile_controls_and_guidance_do_not_change_tour_progress(self):
        guided = self._guided()
        before = deepcopy(guided["tour_state"])
        quiet = extended_profile_control_node(state("不要再问我问题", guided))
        self.assertNotIn("tour_state", quiet)
        self.assertEqual(guided["tour_state"], before)
        self.assertEqual(quiet["visitor_profile"]["interaction_mode"], "listen_only")

        reset = extended_profile_control_node(state("恢复标准讲解", {**guided, **quiet}))
        self.assertEqual(reset["visitor_profile"]["audience_mode"], "standard")
        self.assertEqual(reset["visitor_profile"]["detail_level"], before["detail_level"])
        deleted = extended_profile_control_node(state("删除本次偏好", {**guided, **reset}))
        self.assertIsNone(deleted["visitor_profile"])
        self.assertNotIn("tour_state", deleted)

    def test_confirm_is_only_action_that_writes_visited(self):
        guided = self._guided()
        self.assertEqual(guided["tour_state"]["visited_stop_ids"], [])
        explained = handle_tour_event(guided["tour_state"], guided["tour_interaction_state"], "explanation_finished")
        self.assertEqual(explained["tour_state"]["visited_stop_ids"], [])
        completed = handle_tour_event(explained["tour_state"], explained["interaction_state"], "confirm_stop_complete")
        self.assertEqual(completed["tour_state"]["visited_stop_ids"], ["stop_front_courtyard_center"])

    def test_ambiguous_text_does_not_open_profile_control(self):
        self.assertNotEqual(route_initial_request(state("我们一起看看这里")), "extended_profile_control")


if __name__ == "__main__":
    unittest.main()
