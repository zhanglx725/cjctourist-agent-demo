"""Regression tests for conservative ornament-to-map candidate generation."""

import unittest

from build_ornament_spatial_candidates import build_candidates


class OrnamentSpatialMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_candidates()

    def find(self, name, craft):
        return next(
            row
            for row in self.rows
            if row["ornament_name"] == name and row["craft"] == craft
        )

    def test_every_location_index_entry_is_preserved_for_review(self):
        self.assertEqual(len(self.rows), 105)
        self.assertEqual({row["ornament_id"] for row in self.rows}, {f"orn_{i:03d}" for i in range(1, 106)})

    def test_unambiguous_moon_platform_maps_to_moon_platform_node(self):
        row = self.find("麒麟玉书凤凰图", "砖雕&铜铁铸&壁画")
        self.assertEqual(row["candidate_node_id"], "label_moon_platform")
        self.assertEqual(row["candidate_node_name"], "月台")
        self.assertEqual(row["review_state"], "candidate_ready")

    def test_directional_hall_location_remains_human_review_candidate(self):
        row = self.find("百鸟朝凤", "灰塑")
        self.assertEqual(row["candidate_node_id"], "label_first_west_hall")
        self.assertEqual(row["review_state"], "review_required")

    def test_unmapped_named_corridor_is_not_forced_to_a_nearby_node(self):
        row = self.find("古城会", "灰塑")
        self.assertEqual(row["candidate_node_id"], "")
        self.assertEqual(row["review_state"], "needs_manual_mapping")


if __name__ == "__main__":
    unittest.main()
