import unittest

from qa_context import (
    clear_qa_context,
    create_qa_context,
    is_qa_follow_up_detail_request,
    update_qa_context,
    validate_qa_context,
)


class QaContextTests(unittest.TestCase):
    def setUp(self):
        self.context = create_qa_context(
            query_node_id="label_moon_platform",
            origin="explicit_node",
            subject_kind="craft",
            subject_terms=["石雕"],
            answer_mode="current_point_craft_features",
            follow_up_allowed=True,
            physical_node_id_snapshot="stop_rear_west_courtyard",
        )

    def test_create_has_only_structured_retrieval_conditions(self):
        self.assertEqual(self.context["source_response_kind"], "tour_qa")
        self.assertNotIn("evidence", self.context)
        self.assertNotIn("tour_state", self.context)
        self.assertEqual(self.context["subject_terms"], ("石雕",))

    def test_update_is_immutable(self):
        updated = update_qa_context(self.context, subject_terms=["灰塑"])
        self.assertEqual(self.context["subject_terms"], ("石雕",))
        self.assertEqual(updated["subject_terms"], ("灰塑",))

    def test_invalid_shape_is_rejected_and_clear_is_none(self):
        with self.assertRaises(ValueError):
            validate_qa_context({"query_node_id": "label_moon_platform"})
        self.assertIsNone(clear_qa_context(self.context))

    def test_user_wording_detailed_explanation_is_a_follow_up_request(self):
        self.assertTrue(is_qa_follow_up_detail_request("详细讲讲"))


if __name__ == "__main__":
    unittest.main()
