from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import _next_tour_question_log, route_after_tour_event, visit_summary_node
from narration_coverage import IntroductionRecord, commit_introductions, empty_narration_coverage
from route_planner import plan_template
from tour_state import finish_tour, skip_stop, start_tour
from visit_summary_engine import VisitSummaryError, build_visit_summary


def _record(kind: str, subject: str, node: str, introduced_by: str = "stop_guidance"):
    return IntroductionRecord(kind, subject, ("S08",), introduced_by, node, f"turn-{kind}-{subject}")


class VisitSummaryEngineTests(unittest.TestCase):
    def test_question_audit_counts_only_post_route_qa_turns(self):
        self.assertIsNone(_next_tour_question_log({}, "tour_qa"))
        tour = start_tour(plan_template("highlights_30"))
        first = _next_tour_question_log(
            {"tour_state": tour, "tour_question_log": []}, "tour_qa"
        )
        second = _next_tour_question_log(
            {"tour_state": tour, "tour_question_log": first}, "qa_follow_up_detail"
        )
        self.assertEqual([item["sequence"] for item in second], [1, 2])

    def test_shortcut_detail_is_not_counted_as_a_visitor_question(self):
        tour = start_tour(plan_template("highlights_30"))
        state = {
            "messages": [HumanMessage(content="再讲详细一点")],
            "tour_state": tour,
            "tour_question_log": [],
        }
        self.assertEqual(_next_tour_question_log(state, "qa_follow_up_detail"), [])

    def test_requires_completed_tour(self):
        with self.assertRaises(VisitSummaryError):
            build_visit_summary(start_tour(plan_template("highlights_30")), None, [])

    def test_early_finish_counts_only_visited_stops_and_confirmed_guidance(self):
        tour = start_tour(plan_template("highlights_30"))
        first = tour["route_stop_ids"][0]
        tour["visited_stop_ids"] = [first]
        tour["remaining_stop_ids"] = tour["route_stop_ids"][1:]
        tour["route_status"] = "completed"
        tour["completion_reason"] = "visitor_finished_early"
        coverage = commit_introductions(empty_narration_coverage(), [
            _record("craft", "灰塑", first),
            _record("ornament", "orn_005", first),
            _record("craft", "石雕", tour["route_stop_ids"][1]),
        ])
        summary = build_visit_summary(tour, coverage.to_dict(), []).to_dict()
        self.assertEqual(summary["completion_kind"], "finished_early")
        self.assertEqual(summary["visited_stop_count"], 1)
        self.assertEqual(summary["introduced_craft_ids"], ["灰塑"])
        self.assertEqual(summary["introduced_ornament_ids"], ["orn_005"])
        self.assertNotIn("石雕", summary["message"])

    def test_remote_qa_and_skipped_stop_do_not_count(self):
        tour = start_tour(plan_template("highlights_30"))
        first = tour["route_stop_ids"][0]
        tour = finish_tour(skip_stop(tour, first))
        coverage = commit_introductions(empty_narration_coverage(), [
            _record("craft", "灰塑", first, "tour_qa"),
        ])
        summary = build_visit_summary(tour, coverage.to_dict(), []).to_dict()
        self.assertEqual(summary["visited_stop_count"], 0)
        self.assertEqual(summary["introduced_craft_ids"], [])

    def test_repeated_subjects_are_already_deduplicated_by_coverage(self):
        tour = start_tour(plan_template("highlights_30"))
        first = tour["route_stop_ids"][0]
        tour["visited_stop_ids"] = [first]
        tour["remaining_stop_ids"] = []
        tour["route_status"] = "completed"
        coverage = commit_introductions(empty_narration_coverage(), [
            _record("craft", "灰塑", first), _record("craft", "灰塑", first),
        ])
        summary = build_visit_summary(tour, coverage.to_dict(), []).to_dict()
        self.assertEqual(summary["introduced_craft_ids"], ["灰塑"])

    def test_active_role_commit_counts_after_the_stop_is_actually_completed(self):
        tour = start_tour(plan_template("highlights_30"))
        first = tour["route_stop_ids"][0]
        tour["visited_stop_ids"] = [first]
        tour["remaining_stop_ids"] = []
        tour["route_status"] = "completed"
        coverage = commit_introductions(empty_narration_coverage(), [
            _record("craft", "灰塑", first, "narration_commit"),
            _record("ornament", "orn_005", first, "narration_commit"),
        ])
        summary = build_visit_summary(tour, coverage.to_dict(), []).to_dict()
        self.assertEqual(summary["introduced_craft_ids"], ["灰塑"])
        self.assertEqual(summary["introduced_ornament_ids"], ["orn_005"])

    def test_malformed_coverage_omits_exact_content_counts(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        summary = build_visit_summary(tour, {"bad": True}, []).to_dict()
        self.assertEqual(summary["coverage_status"], "unavailable")
        self.assertIn("不报告具体工艺或题材数量", summary["message"])

    def test_completed_event_routes_to_summary_without_rewriting_sources(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        state = {
            "tour_state": tour,
            "narration_coverage": empty_narration_coverage().to_dict(),
            "tour_question_log": [],
            "last_tour_event": {"ok": True, "event": "finish_tour", "code": "tour_finished"},
        }
        self.assertEqual(route_after_tour_event(state), "visit_summary")
        update = visit_summary_node(state)
        self.assertEqual(update["visit_summary"]["completion_kind"], "finished_early")
        self.assertNotIn("tour_state", update)
        self.assertNotIn("narration_coverage", update)
        self.assertTrue(update["visit_summary_evaluations"][-1]["tour_state_preserved"])

    def test_question_count_uses_only_valid_current_route_qa_audit(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        route_id = tour["selected_route_id"]
        summary = build_visit_summary(
            tour,
            empty_narration_coverage().to_dict(),
            [
                {"sequence": 1, "route_id": route_id, "node": "tour_qa"},
                {"sequence": 2, "route_id": route_id, "node": "qa_follow_up_detail"},
            ],
        ).to_dict()
        self.assertEqual(summary["question_count"], 2)
        self.assertEqual(summary["question_count_status"], "available")
        self.assertIn("共提出了 2 次问题", summary["message"])

    def test_invalid_question_audit_omits_exact_count(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        summary = build_visit_summary(
            tour, empty_narration_coverage().to_dict(),
            [{"sequence": 1, "route_id": "other-route", "node": "tour_qa"}],
        ).to_dict()
        self.assertIsNone(summary["question_count"])
        self.assertEqual(summary["question_count_status"], "unavailable")

    def test_title_basis_combines_heard_topics_questions_and_explicit_profile(self):
        tour = start_tour(plan_template("highlights_30"), interests=["灰塑", "木雕"])
        first = tour["route_stop_ids"][0]
        tour["visited_stop_ids"] = [first]
        tour["remaining_stop_ids"] = []
        tour["route_status"] = "completed"
        coverage = commit_introductions(empty_narration_coverage(), [
            _record("craft", "灰塑", first),
            _record("ornament", "orn_005", first),
        ])
        summary = build_visit_summary(
            tour,
            coverage.to_dict(),
            [{"sequence": 1, "route_id": tour["selected_route_id"], "node": "tour_qa"}],
            {
                "available_minutes": 30,
                "interests": ["灰塑", "木雕"],
                "detail_level": "standard",
                "explanation_style": "story",
            },
        ).to_dict()
        basis = summary["title_basis"]
        self.assertEqual(basis["question_count"], 1)
        self.assertEqual(basis["explicit_interest_ids"], ["灰塑", "木雕"])
        self.assertEqual(basis["matched_interest_ids"], ["灰塑"])
        self.assertEqual(basis["explanation_style"], "story")
        self.assertIn("独角狮", basis["introduced_topic_names"])

    def test_neutral_profile_defaults_are_not_title_achievement_signals(self):
        tour = finish_tour(start_tour(plan_template("highlights_30")))
        summary = build_visit_summary(
            tour, empty_narration_coverage().to_dict(), [],
            {"available_minutes": 30, "interests": [], "detail_level": "standard"},
        ).to_dict()
        basis = summary["title_basis"]
        self.assertIsNone(basis["explanation_style"])
        self.assertIsNone(basis["interaction_mode"])
        self.assertIsNone(basis["knowledge_level"])


if __name__ == "__main__":
    unittest.main()
