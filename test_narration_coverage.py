"""Offline unit and lifecycle tests for E5-A1 NarrationCoverage."""

from __future__ import annotations

import unittest

from langchain_core.messages import HumanMessage

from agent_graph import agent_graph, direct_route_node
from narration_coverage import (
    IntroductionRecord,
    NarrationCoverageError,
    clear_narration_coverage,
    commit_introductions,
    empty_narration_coverage,
    is_craft_introduced,
    is_ornament_introduced,
    load_narration_coverage,
)
from tour_interaction import handle_tour_event


def _record(kind: str = "craft", subject_id: str = "灰塑", **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "subject_kind": kind,
        "subject_id": subject_id,
        "source_ids": ["S07"],
        "introduced_by": "stop_guidance",
        "node_id": "stop_front_courtyard_center",
        "turn_id": "turn:1",
    }
    record.update(changes)
    return record


def _message_state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class NarrationCoverageTests(unittest.TestCase):
    def test_empty_state_and_legacy_missing_field_are_compatible(self):
        coverage = empty_narration_coverage()
        self.assertEqual(coverage.to_dict()["introduced_craft_ids"], [])
        self.assertEqual(load_narration_coverage(None), coverage)

    def test_dict_round_trip_is_stable(self):
        coverage = commit_introductions(None, [_record(), _record("ornament", "orn_005", source_ids=["S08"])])
        self.assertEqual(load_narration_coverage(coverage.to_dict()).to_dict(), coverage.to_dict())

    def test_legal_craft_and_ornament_records_commit(self):
        coverage = commit_introductions(None, [_record(), _record("ornament", "orn_005", source_ids=["S08"])])
        self.assertTrue(is_craft_introduced(coverage, "灰塑"))
        self.assertTrue(is_ornament_introduced(coverage, "orn_005"))

    def test_duplicate_submission_is_idempotent_and_preserves_first_audit_record(self):
        first = commit_introductions(None, [_record(node_id="stop_front_courtyard_center", turn_id="turn:1")])
        repeated = commit_introductions(first, [_record(node_id="label_moon_platform", turn_id="turn:2", source_ids=["S99"])])
        self.assertEqual(repeated, first)

    def test_invalid_kind_and_empty_sources_fail_closed(self):
        with self.assertRaises(NarrationCoverageError):
            commit_introductions(None, [_record(kind="fact")])
        with self.assertRaises(NarrationCoverageError):
            commit_introductions(None, [_record(source_ids=[])])

    def test_batch_with_one_invalid_record_is_atomic(self):
        initial = commit_introductions(None, [_record()])
        with self.assertRaises(NarrationCoverageError):
            commit_introductions(initial, [_record("ornament", "orn_005", source_ids=["S08"]), _record(kind="invalid")])
        self.assertEqual(initial.introduced_ornament_ids, ())

    def test_clear_returns_fresh_empty_snapshot(self):
        coverage = commit_introductions(None, [_record()])
        cleared = clear_narration_coverage(coverage)
        self.assertEqual(cleared, empty_narration_coverage())
        self.assertNotEqual(cleared, coverage)

    def test_coverage_operations_do_not_mutate_tour_or_profile_snapshots(self):
        tour_state = {"current_stop_id": "stop_front_courtyard_center", "visited_stop_ids": []}
        visitor_profile = {"available_minutes": 30, "interests": ["灰塑"], "detail_level": "standard"}
        before_tour = dict(tour_state)
        before_profile = dict(visitor_profile)
        commit_introductions(None, [_record()])
        self.assertEqual(tour_state, before_tour)
        self.assertEqual(visitor_profile, before_profile)

    def test_new_route_initialization_clears_existing_coverage(self):
        prior = commit_introductions(None, [_record()]).to_dict()
        result = direct_route_node(_message_state("我有30分钟，帮我规划路线", {"narration_coverage": prior}))
        self.assertEqual(result["narration_coverage"], empty_narration_coverage().to_dict())

    def test_arrival_skip_and_replanning_do_not_clear_coverage(self):
        initial = direct_route_node(_message_state("我有30分钟，帮我规划路线"))
        coverage = commit_introductions(None, [_record()]).to_dict()
        initial["narration_coverage"] = coverage
        arrived = handle_tour_event(initial["tour_state"], initial["tour_interaction_state"], "arrive_at_stop", node_id=initial["tour_interaction_state"]["pending_stop_id"])
        skipped = handle_tour_event(initial["tour_state"], initial["tour_interaction_state"], "skip_stop", node_id=initial["tour_interaction_state"]["pending_stop_id"])
        replanned = handle_tour_event(initial["tour_state"], initial["tour_interaction_state"], "replan_time", available_minutes=20)
        self.assertEqual(initial["narration_coverage"], coverage)
        self.assertTrue(arrived["ok"])
        self.assertTrue(skipped["ok"])
        self.assertTrue(replanned["ok"])

    def test_threads_are_isolated_and_coverage_does_not_change_tour_or_profile(self):
        first_config = {"configurable": {"thread_id": "e5-a1-coverage-a"}}
        second_config = {"configurable": {"thread_id": "e5-a1-coverage-b"}}
        agent_graph.invoke(
            {"messages": [("user", "查看当前画像")], "tool_loops": 0, "retrieved_evidence": [], "performance_metrics": []},
            config=first_config,
        )
        agent_graph.invoke(
            {"messages": [("user", "查看当前画像")], "tool_loops": 0, "retrieved_evidence": [], "performance_metrics": []},
            config=second_config,
        )
        agent_graph.update_state(first_config, {"narration_coverage": commit_introductions(None, [_record()]).to_dict()})
        first = agent_graph.get_state(first_config).values
        second = agent_graph.get_state(second_config).values
        self.assertTrue(is_craft_introduced(first.get("narration_coverage"), "灰塑"))
        self.assertIsNone(second.get("narration_coverage"))
        self.assertNotIn("tour_state", first)
        self.assertNotIn("visitor_profile", first)


if __name__ == "__main__":
    unittest.main()
