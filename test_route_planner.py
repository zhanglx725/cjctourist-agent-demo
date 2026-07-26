import unittest

from route_planner import plan_template, recommend_route


class RoutePlannerTests(unittest.TestCase):
    def test_all_reviewed_templates_expand_to_walkable_paths(self):
        for route_id in ("highlights_30", "crafts_60", "deep_dive_90"):
            plan = plan_template(route_id)
            self.assertEqual(plan.stop_ids[0], "entrance_main_outside")
            self.assertGreater(len(plan.full_path_node_ids), len(plan.stop_ids))
            self.assertGreater(len(plan.edge_ids), 0)
            self.assertIsNotNone(plan.estimated_walk_seconds)
            self.assertEqual(plan.full_path_node_ids[-1], "stop_front_courtyard_center")
            self.assertIsNotNone(plan.estimated_exit_return_seconds)

    def test_each_template_uses_only_one_front_axis_stop(self):
        front_axis = {"stop_front_courtyard_north", "label_moon_platform"}
        for route_id in ("highlights_30", "crafts_60", "deep_dive_90"):
            plan = plan_template(route_id)
            self.assertLessEqual(len(front_axis.intersection(plan.stop_ids)), 1)

    def test_plan_has_explicit_estimated_time_warning(self):
        plan = plan_template("highlights_30")
        self.assertTrue(any("待现场实测" in warning for warning in plan.warnings))

    def test_plan_counts_observation_and_interaction_time(self):
        plan = plan_template("highlights_30")
        self.assertEqual(plan.estimated_observation_seconds, 270)
        self.assertEqual(plan.estimated_interaction_seconds, 360)
        self.assertGreater(plan.estimated_total_seconds, plan.estimated_explanation_seconds)

    def test_recommendation_respects_available_time(self):
        plan = recommend_route(available_minutes=30, interests=["工艺"])
        self.assertEqual(plan.route_id, "highlights_30")


if __name__ == "__main__":
    unittest.main()
