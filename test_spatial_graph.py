"""Tests for the reviewed spatial-network MVP."""

import unittest

from spatial_graph import build_spatial_graph, shortest_route, unreachable_guide_stops


class SpatialGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_spatial_graph()

    def test_every_reviewed_edge_is_bidirectional(self):
        for start, end in self.graph.edges:
            self.assertTrue(self.graph.has_edge(end, start))

    def test_all_guide_stops_are_reachable_from_main_entrance(self):
        self.assertEqual(unreachable_guide_stops(graph=self.graph), [])

    def test_official_route_backbone_reaches_juxian_hall(self):
        route = shortest_route(
            "entrance_main_outside", "stop_juxian_hall", graph=self.graph
        )
        self.assertEqual(route.names[0], "大门外")
        self.assertEqual(route.names[-1], "中进聚贤堂")
        self.assertIn("首进正厅", route.names)
        self.assertIn("月台", route.names)
        self.assertIsNotNone(route.estimated_walk_seconds)
        self.assertIn("estimated_from_map_and_official_route", route.walk_time_basis)


if __name__ == "__main__":
    unittest.main()
