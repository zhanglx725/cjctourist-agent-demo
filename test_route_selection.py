"""Offline regression tests for E4-3B multi-objective route selection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from route_planner import plan_template
from route_selection import (
    RouteCandidateEvaluation,
    _select_highest_scored_candidate,
    derive_interest_coverage,
    recommend_route,
)


class RouteSelectionTests(unittest.TestCase):
    def test_highest_scored_qualified_candidate_is_selected_without_anchor_margin(self):
        anchor = RouteCandidateEvaluation(
            candidate_id="highlights_30",
            route_strategy="anchor",
            guide_stop_ids=("stop_front_courtyard_center",),
            estimated_total_seconds=1700,
            requested_minutes=30,
            detail_level="standard",
            interest_evidence={},
            components={
                "time_utilization": 0.9,
                "interest_coverage": 1.0,
                "detail_fit": 1.0,
                "walking_cost": 0.9,
                "reviewed_anchor_bonus": 1.0,
            },
            total_score=0.815,
        )
        dynamic = RouteCandidateEvaluation(
            candidate_id="dynamic_30",
            route_strategy="dynamic",
            guide_stop_ids=("stop_front_courtyard_north",),
            estimated_total_seconds=1650,
            requested_minutes=30,
            detail_level="standard",
            interest_evidence={},
            components={
                "time_utilization": 0.91,
                "interest_coverage": 1.0,
                "detail_fit": 1.0,
                "walking_cost": 0.9,
                "reviewed_anchor_bonus": 0.0,
            },
            total_score=0.794,
        )
        selected, _ = _select_highest_scored_candidate([(dynamic, object()), (anchor, object())])
        self.assertEqual(selected.candidate_id, "highlights_30")

    def test_deep_ninety_minute_route_uses_productive_time_and_object_evidence(self):
        result = recommend_route(90, interests=["灰塑", "木雕"], detail_level="deep")
        self.assertEqual(result.status, "selected")
        selected = result.selected
        assert selected is not None
        self.assertLessEqual(selected.estimated_total_seconds, 90 * 60)
        ratio = selected.estimated_total_seconds / (90 * 60)
        self.assertGreaterEqual(ratio, 0.80)
        self.assertLessEqual(ratio, 0.95)
        covered = selected.selection_reason["covered_interests"]
        self.assertIn("灰塑", covered)
        self.assertIn("木雕", covered)

    def test_interest_evidence_is_derived_from_actual_reviewed_stop_objects(self):
        result = recommend_route(60, interests=["灰塑", "木雕"], detail_level="standard")
        selected = result.selected
        assert selected is not None
        evidence = derive_interest_coverage(selected.guide_stop_ids, ["灰塑", "木雕"])
        for interest, matches in evidence.items():
            self.assertTrue(matches, interest)
            self.assertTrue(all(item["node_id"] in selected.guide_stop_ids for item in matches))
            self.assertTrue(
                all(interest in item["craft"] or interest in item["name"] for item in matches)
            )

    def test_non_anchor_duration_keeps_dynamic_route_available(self):
        result = recommend_route(45, interests=["灰塑"], detail_level="standard")
        self.assertEqual(result.status, "selected")
        selected = result.selected
        assert selected is not None
        self.assertEqual(selected.route_strategy, "dynamic")
        self.assertLessEqual(selected.estimated_total_seconds, 45 * 60)

    def test_suitable_anchor_remains_an_auditable_candidate_not_a_forced_output(self):
        result = recommend_route(30, interests=[], detail_level="standard")
        self.assertEqual(result.status, "selected")
        selected = result.selected
        assert selected is not None
        self.assertLessEqual(selected.estimated_total_seconds, 30 * 60)
        anchors = [item for item in result.evaluations if item.route_strategy == "anchor"]
        self.assertTrue(anchors)
        self.assertEqual(anchors[0].candidate_id, "highlights_30")

    def test_selected_route_reason_and_evaluation_gap_are_consistent(self):
        result = recommend_route(30, interests=["灰塑"], detail_level="standard")
        selected = result.selected
        assert selected is not None
        selected_evaluation = next(
            item for item in result.evaluations if item.candidate_id == selected.route_id
        )
        self.assertEqual(selected_evaluation.gap_from_best_score, 0.0)
        self.assertEqual(selected.selection_reason["gap_from_best_score"], 0.0)
        self.assertEqual(
            selected.selection_reason["selected_total_score"], selected_evaluation.total_score
        )

    def test_invalid_dynamic_candidate_falls_back_to_qualified_anchor(self):
        with patch("route_selection.plan_dynamic_route", side_effect=ValueError("broken dynamic data")):
            result = recommend_route(30, interests=[], detail_level="standard")
        self.assertEqual(result.status, "selected")
        self.assertIsNotNone(result.selected)
        assert result.selected is not None
        self.assertEqual(result.selected.route_strategy, "anchor")
        self.assertTrue(
            any(item.rejected_reason and "dynamic_candidate_unavailable" in item.rejected_reason
                for item in result.evaluations)
        )

    def test_all_unqualified_candidates_return_structured_no_route_result(self):
        over_budget_anchor = plan_template("highlights_30")
        with patch("route_selection._anchor_candidates", return_value=[("highlights_30", over_budget_anchor)]), \
             patch("route_selection.plan_dynamic_route", side_effect=ValueError("broken dynamic data")):
            result = recommend_route(20, interests=[], detail_level="standard")
        self.assertEqual(result.status, "no_qualified_route")
        self.assertIsNone(result.selected)
        self.assertEqual(result.reason_code, "no_reviewed_candidate_within_strict_budget")

    def test_same_input_is_stable_and_state_free(self):
        first = recommend_route(75, interests=["木雕", "灰塑"], detail_level="standard")
        second = recommend_route(75, interests=["灰塑", "木雕"], detail_level="standard")
        self.assertEqual(first.status, "selected")
        self.assertEqual(second.status, "selected")
        assert first.selected is not None and second.selected is not None
        self.assertEqual(first.selected.route_id, second.selected.route_id)
        self.assertEqual(first.selected.guide_stop_ids, second.selected.guide_stop_ids)
        self.assertEqual(first.selected.selection_reason, second.selected.selection_reason)

    def test_no_interest_prefers_time_fit_without_exceeding_budget(self):
        result = recommend_route(30, interests=[], detail_level="standard")
        self.assertEqual(result.status, "selected")
        selected = result.selected
        assert selected is not None
        self.assertLessEqual(selected.estimated_total_seconds, 30 * 60)
        self.assertEqual(selected.selection_reason["uncovered_interests"], [])


if __name__ == "__main__":
    unittest.main()
