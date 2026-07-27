"""Offline schema and frozen-boundary checks for the D-stage acceptance matrix.

These tests deliberately validate the shared acceptance contract rather than
repeating D1--D6 implementation tests.  The functional behaviour remains in
the module-specific test suites; this file prevents later edits from silently
changing what D-stage review is expected to prove.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import unittest

import yaml


CASES_FILE = Path("data/chen_clan_academy/evaluation/d_stage_acceptance_cases_v1.yaml")
ROUTES = {"tour_qa", "tour_event", "direct_rag"}
CARD_TYPES = {"glossary_term", "research_summary", "comparison_card", "photo_spot_card", "base_rag", "none"}
KNOWLEDGE_CATEGORIES = {
    "term_definition", "term_translation", "draft_translation_block",
    "research_attribution", "research_limit", "comparison_general",
    "comparison_research", "photo_current_point", "photo_whole_site",
    "photo_family", "photo_solo", "platform_isolation",
    "photo_no_candidate_fallback", "multi_intent_clarification",
    "damaged_data_fallback", "thread_isolation",
}
INTERNAL_TOKENS = ("card_id", "runtime_status", "claim_strength", ".yaml", ".pdf", "platform_observation")


class DStageAcceptanceCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
        cls.cases = cls.document["cases"]

    def test_header_declares_pending_human_validation_without_claiming_completion(self) -> None:
        self.assertEqual(self.document["schema_version"], "d_stage_acceptance_cases_v1")
        self.assertEqual(self.document["module"], "d_stage")
        self.assertEqual(self.document["review_status"], "pending_local_and_langsmith_validation")
        self.assertIsNone(self.document["reviewer"])
        self.assertIsNone(self.document["reviewed_at"])

    def test_case_ids_are_unique_contiguous_and_frozen(self) -> None:
        ids = [case["case_id"] for case in self.cases]
        self.assertEqual(ids, [f"dst_acc_{number:03d}" for number in range(1, 18)])
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_has_the_required_review_fields(self) -> None:
        required = {
            "case_id", "category", "input", "precondition_tour_state",
            "precondition_visitor_profile", "expected_route", "expected_card_type",
            "must_include", "must_not_include", "allowed_state_changes",
            "expected_sources", "manual_review_status",
        }
        for case in self.cases:
            self.assertTrue(required.issubset(case))
            self.assertIn(case["expected_route"], ROUTES)
            self.assertIn(case["expected_card_type"], CARD_TYPES)
            self.assertEqual(case["manual_review_status"], "pending")
            for phrase in case["must_include"]:
                self.assertFalse(any(token in phrase for token in INTERNAL_TOKENS))

    def test_matrix_covers_every_d_substage_and_required_safety_cases(self) -> None:
        categories = Counter(case["category"] for case in self.cases)
        for category in (
            "term_definition", "term_translation", "draft_translation_block",
            "research_attribution", "research_limit", "comparison_general",
            "comparison_research", "photo_current_point", "photo_whole_site",
            "photo_family", "photo_solo", "platform_isolation",
            "photo_no_candidate_fallback", "tour_event_lifecycle",
            "multi_intent_clarification", "damaged_data_fallback", "thread_isolation",
        ):
            self.assertEqual(categories[category], 1)

    def test_only_explicit_tour_event_case_may_change_execution_state(self) -> None:
        for case in self.cases:
            if case["category"] in KNOWLEDGE_CATEGORIES:
                self.assertEqual(case["allowed_state_changes"], [])
            else:
                self.assertEqual(case["category"], "tour_event_lifecycle")
                self.assertNotIn("visited_stop_ids", case["allowed_state_changes"])

    def test_experience_and_internal_content_are_never_acceptance_outputs(self) -> None:
        for case in self.cases:
            for phrase in [*case["must_include"], *case["must_not_include"]]:
                self.assertFalse("/" in phrase or "\\" in phrase)
        photo_cases = [case for case in self.cases if case["category"].startswith("photo_")]
        for case in photo_cases:
            self.assertIn("热门", case["must_not_include"])
            self.assertIn("最佳", case["must_not_include"])
            self.assertIn("一定能拍到", case["must_not_include"])
        platform = next(case for case in self.cases if case["category"] == "platform_isolation")
        self.assertIn("platform_observation", platform["must_not_include"])


if __name__ == "__main__":
    unittest.main()
