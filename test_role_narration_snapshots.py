from __future__ import annotations

import unittest

from tools.capture_role_narration_snapshots import DEFAULT_STYLES, build_snapshot_cases


class RoleNarrationSnapshotTests(unittest.TestCase):
    def test_default_contrast_matrix_has_three_reviewed_point_types_per_style(self):
        cases = build_snapshot_cases(DEFAULT_STYLES)
        self.assertEqual(len(cases), 12)
        for style_id in DEFAULT_STYLES:
            point_types = {
                item["inputs"]["point_type"]
                for item in cases
                if item["inputs"]["style_id"] == style_id
            }
            self.assertEqual(point_types, {"building", "craft", "ornament"})

    def test_unknown_style_fails_before_model_invocation(self):
        with self.assertRaisesRegex(ValueError, "Unknown or unapproved"):
            build_snapshot_cases(("buddy_guide", "not-a-style"))


if __name__ == "__main__":
    unittest.main()
