"""Pure contract tests for same-name ornament choice state."""

from __future__ import annotations

import unittest

from ornament_clarification import (
    create_pending_ornament_clarification,
    resolve_pending_ornament_choice,
)


class OrnamentClarificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pending = create_pending_ornament_clarification(
            original_query="讲讲同名构件的故事。",
            subject_name="同名构件",
            requested_detail="story",
            evidence_scope="exact_ornament",
            candidates=[
                {
                    "choice_index": 1, "candidate_kind": "ambiguous_group",
                    "display_name": "同名构件", "craft": "木雕",
                    "node_id": "test_node", "node_name": "测试点",
                    "member_ornament_ids": ["orn_test_001", "orn_test_002"],
                    "selectable_for_exact_detail": False,
                },
                {
                    "choice_index": 2, "candidate_kind": "exact_object",
                    "display_name": "同名构件", "craft": "石雕",
                    "node_id": "test_node", "node_name": "测试点",
                    "ornament_id": "orn_test_003", "selectable_for_exact_detail": True,
                },
            ],
        )

    def test_stable_index_and_craft_resolve_without_selecting_group_members(self):
        self.assertEqual(resolve_pending_ornament_choice("第二个", self.pending)["candidate"]["ornament_id"], "orn_test_003")
        self.assertEqual(resolve_pending_ornament_choice("石雕那个", self.pending)["status"], "selected")
        wood = resolve_pending_ornament_choice("木雕", self.pending)
        self.assertEqual(wood["status"], "data_ambiguity")
        self.assertNotIn("ornament_id", wood["candidate"])

    def test_invalid_or_ambiguous_selection_never_guesses(self):
        self.assertEqual(resolve_pending_ornament_choice("都行", self.pending)["status"], "unresolved")
        self.assertEqual(resolve_pending_ornament_choice("第三个", self.pending)["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
