from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import (
    post_visit_title_blessing_node,
    route_after_visit_summary,
    route_initial_request,
    visit_summary_node,
)
from narration_coverage import empty_narration_coverage
from post_visit_award import PostVisitAwardError, build_post_visit_award, is_post_visit_request
from route_planner import plan_template
from tour_state import finish_tour, start_tour


def _summary(**basis):
    value = {
        "completion_kind": "finished_early", "visited_stop_count": 1,
        "introduced_craft_ids": [], "introduced_topic_names": [],
        "content_diversity_count": 0, "question_count": 0,
        "matched_interest_ids": [], "explanation_style": None,
    }
    value.update(basis)
    return {"schema_version": "visit_summary_v1", "title_basis": value}


class PostVisitAwardTests(unittest.TestCase):
    def test_question_rule_has_fixed_priority_and_original_blessing(self):
        award = build_post_visit_award(_summary(question_count=3, matched_interest_ids=["灰塑", "木雕"]))
        self.assertEqual(award["title_id"], "curious_explorer")
        self.assertIn("3 次问题", award["reason"])
        self.assertIn("趣味纪念称号", award["disclaimer"])

    def test_interest_story_completion_and_neutral_rules_are_deterministic(self):
        cases = [
            (_summary(matched_interest_ids=["灰塑", "木雕"]), "interest_connoisseur"),
            (_summary(explanation_style="story", introduced_topic_names=["独角狮", "福禄寿"]), "story_tracer"),
            (_summary(completion_kind="completed_all_stops", visited_stop_count=3), "route_finisher"),
            (_summary(), "mindful_visitor"),
        ]
        for summary, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(build_post_visit_award(summary)["title_id"], expected)

    def test_invalid_summary_fails_closed(self):
        with self.assertRaises(PostVisitAwardError):
            build_post_visit_award(None)

    def test_post_visit_request_parser_is_narrow(self):
        self.assertTrue(is_post_visit_request("给我一个专属称号和祝福"))
        self.assertTrue(is_post_visit_request("查看游览总结"))
        self.assertFalse(is_post_visit_request("开始导游"))

    def test_summary_chains_to_award_without_protected_state_writes(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        state = {
            "tour_state": tour,
            "visitor_profile": {"available_minutes": 30, "interests": [], "detail_level": "standard"},
            "narration_coverage": empty_narration_coverage().to_dict(),
            "tour_question_log": [],
        }
        summary_update = visit_summary_node(state)
        self.assertEqual(route_after_visit_summary(summary_update), "post_visit_title_blessing")
        award_update = post_visit_title_blessing_node({**state, **summary_update})
        self.assertIn("称号", award_update["messages"][0].content)
        self.assertIn("祝福", award_update["messages"][0].content)
        for field in ("tour_state", "visitor_profile", "narration_coverage"):
            self.assertNotIn(field, award_update)

    def test_completed_tour_requests_never_restart_mode_selection(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        base = {
            "tour_state": tour,
            "visit_summary": _summary(),
        }
        for text in ("结束游览", "给我一个专属称号和祝福"):
            with self.subTest(text=text):
                state = {**base, "messages": [HumanMessage(content=text)]}
                self.assertEqual(
                    route_initial_request(state), "post_visit_title_blessing"
                )


if __name__ == "__main__":
    unittest.main()
