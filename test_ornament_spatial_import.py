import unittest

from import_reviewed_ornament_mapping import (
    build_mapping_rows,
    new_node_key,
    normalise_decision,
)


class ReviewedOrnamentImportTests(unittest.TestCase):
    def test_add_node_variants_are_normalised(self):
        self.assertEqual(normalise_decision("`add_node`"), "add_node")
        self.assertEqual(normalise_decision("add_nodes"), "add_node")

    def test_add_node_reuses_registered_node(self):
        rows = build_mapping_rows(
            [
                {
                    "ornament_id": "orn_test",
                    "ornament_name": "测试装饰",
                    "craft": "灰塑",
                    "raw_location": "后东庭",
                    "reviewer_decision": "add_nodes",
                    "final_node_id": "",
                    "review_notes": "后东庭，新增点",
                }
            ],
            {"stop_rear_east_courtyard_inner"},
            {"后东庭": "stop_rear_east_courtyard_inner"},
        )
        self.assertEqual(rows[0]["final_node_id"], "stop_rear_east_courtyard_inner")
        self.assertEqual(rows[0]["mapping_source"], "manual_review_registered_add_node")

    def test_note_key_uses_text_before_comma(self):
        self.assertEqual(new_node_key("前院西部靠中，新增点"), "前院西部靠中")


if __name__ == "__main__":
    unittest.main()
