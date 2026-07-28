import unittest

from dynamic_route_planner import (
    eligible_dynamic_stops,
    filter_dynamic_candidates,
    plan_dynamic_route,
    score_candidate,
)


class DynamicRouteCandidateTests(unittest.TestCase):
    def test_only_approved_ornament_rich_stops_are_eligible(self):
        candidates = eligible_dynamic_stops()
        self.assertEqual(len(candidates), 12)
        self.assertTrue(all(item.mapped_ornament_count >= 4 for item in candidates))
        self.assertNotIn("entrance_main_outside", {item.node_id for item in candidates})

    def test_all_candidates_are_reachable_from_entrance(self):
        candidates = filter_dynamic_candidates()
        self.assertEqual(len(candidates), 12)

    def test_explicit_exclusion_removes_candidate(self):
        candidates = filter_dynamic_candidates(excluded_stop_ids=["label_moon_platform"])
        self.assertNotIn("label_moon_platform", {item.node_id for item in candidates})

    def test_front_axis_conflict_is_exposed_to_later_selector(self):
        candidates = {item.node_id: item for item in eligible_dynamic_stops()}
        self.assertIn("front_axis_observation", candidates["label_moon_platform"].conflict_groups)
        self.assertIn("front_axis_observation", candidates["stop_front_courtyard_north"].conflict_groups)

    def test_interest_changes_content_score(self):
        candidates = {item.node_id: item for item in eligible_dynamic_stops()}
        west = candidates["stop_rear_west_courtyard"]
        east = candidates["stop_front_east_courtyard"]
        self.assertGreater(
            score_candidate(west, interests=["三国"]).total,
            score_candidate(east, interests=["三国"]).total,
        )

    def test_dynamic_45_minute_route_is_reachable_and_within_budget(self):
        route = plan_dynamic_route(45, interests=["灰塑"])
        self.assertGreaterEqual(len(route.stop_ids), 3)
        self.assertLessEqual(route.estimated_total_seconds, route.allowed_total_seconds)
        self.assertEqual(route.full_path_node_ids[0], "entrance_main_outside")
        self.assertEqual(route.full_path_node_ids[-1], "stop_front_courtyard_center")
        self.assertGreater(route.estimated_exit_return_seconds, 0)
        self.assertEqual(len(route.edge_ids), len(route.full_path_node_ids) - 1)

    def test_dynamic_route_does_not_select_front_axis_conflict_pair(self):
        route = plan_dynamic_route(45, interests=["工艺"])
        self.assertFalse(
            {"label_moon_platform", "stop_front_courtyard_north"}.issubset(route.stop_ids)
        )

    def test_three_kingdoms_interest_keeps_a_relevant_story_stop(self):
        route = plan_dynamic_route(45, interests=["三国"])
        self.assertTrue(
            {"stop_rear_west_courtyard", "stop_front_courtyard_west_inner"}
            .intersection(route.stop_ids)
        )

    def test_deep_dynamic_route_uses_the_deep_experience_budget_with_strict_cap(self):
        route = plan_dynamic_route(90, interests=["灰塑", "木雕"], detail_level="deep")
        self.assertEqual(route.detail_level, "deep")
        self.assertLessEqual(route.estimated_total_seconds, 90 * 60)
        self.assertGreater(route.estimated_interaction_seconds, 0)


if __name__ == "__main__":
    unittest.main()
