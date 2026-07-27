"""Offline schema checks for D2 glossary acceptance scenarios."""

from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).parent
DATA = ROOT / "data" / "chen_clan_academy"
CASES_FILE = DATA / "glossary" / "glossary_acceptance_cases_v1.yaml"
GLOSSARY_FILE = DATA / "glossary" / "glossary_zh_en_v0.yaml"
ELIGIBILITY_FILE = DATA / "card_runtime_eligibility_knowledge_v1.yaml"
ASSOCIATIONS_FILE = DATA / "routes" / "term_stop_associations_v1.json"
MARKERS_FILE = DATA / "spatial" / "marker_inventory_v0.csv"

CATEGORIES = {
    "definition_zh", "translation_en", "pinyin", "domain", "alias",
    "node_boost", "ambiguity", "draft_block", "negative_route", "rag_fallback",
}
ROUTES = {"tour_qa", "not_glossary"}
INTERNAL_EXPECTATION_TOKENS = ("runtime_status", "source_ids", "card_id", "term_id", "data/", ".yaml", ".json")


class GlossaryAcceptanceCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
        cls.cases = cls.data["cases"]
        glossary = yaml.safe_load(GLOSSARY_FILE.read_text(encoding="utf-8"))
        cls.terms = {term["term_id"]: term for term in glossary["terms"]}
        eligibility = yaml.safe_load(ELIGIBILITY_FILE.read_text(encoding="utf-8"))
        cls.eligibility = {item["card_id"]: item for item in eligibility["cards"]}
        associations = json.loads(ASSOCIATIONS_FILE.read_text(encoding="utf-8"))
        cls.association_nodes = {item["node_id"] for item in associations["associations"]}
        marker_ids = set(re.findall(r"^([^,\r\n]+),", MARKERS_FILE.read_text(encoding="utf-8"), re.MULTILINE))
        cls.node_ids = cls.association_nodes | marker_ids

    def test_yaml_parses_and_has_required_header(self) -> None:
        self.assertEqual(self.data["schema_version"], "glossary_acceptance_cases_v1")
        self.assertEqual(self.data["module"], "glossary")
        self.assertEqual(self.data["review_status"], "draft")
        self.assertIsNone(self.data["reviewer"])
        self.assertIsNone(self.data["reviewed_at"])

    def test_case_ids_are_unique_and_contiguous(self) -> None:
        ids = [case["case_id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"gls_acc_{number:03d}" for number in range(1, len(ids) + 1)])

    def test_categories_routes_and_case_status_are_controlled(self) -> None:
        for case in self.cases:
            self.assertIn(case["category"], CATEGORIES)
            self.assertIn(case["expected_route"], ROUTES)
            self.assertIn(case["case_status"], {"reviewed", "draft"})

    def test_referenced_terms_and_nodes_exist(self) -> None:
        for case in self.cases:
            self.assertTrue(set(case["expected_term_ids"]).issubset(self.terms))
            node_id = case["current_node_id"]
            if node_id is not None:
                self.assertIn(node_id, self.node_ids)

    def test_positive_english_cases_require_enabled_translation_capability(self) -> None:
        for case in self.cases:
            if case["category"] != "translation_en":
                continue
            self.assertTrue(case["expected_term_ids"])
            for term_id in case["expected_term_ids"]:
                card = self.eligibility[term_id]
                self.assertEqual(card["runtime_status"], "enabled")
                self.assertIn("en_translation", card["allowed_capabilities"])

    def test_draft_terms_only_appear_in_negative_draft_cases(self) -> None:
        draft_ids = {term_id for term_id, term in self.terms.items() if term["translation_status"] == "draft"}
        for case in self.cases:
            used_drafts = set(case["expected_term_ids"]) & draft_ids
            if used_drafts:
                self.assertEqual(case["category"], "draft_block")
                self.assertNotIn("en_translation", case["required_capabilities"])

    def test_negative_routes_and_tour_state_boundaries(self) -> None:
        for case in self.cases:
            self.assertTrue(case["expected_behavior"]["tour_state_must_remain_unchanged"])
            if case["category"] == "negative_route":
                self.assertEqual(case["expected_route"], "not_glossary")

    def test_node_cases_declare_visibility_boundary(self) -> None:
        for case in self.cases:
            if case["current_node_id"] is not None or case["category"] == "node_boost":
                self.assertTrue(case["visibility_boundary"].strip())
            if case["category"] == "node_boost":
                self.assertTrue(case["expected_behavior"]["current_node_only_boosts_ranking"])

    def test_expectations_do_not_expose_paths_or_internal_fields(self) -> None:
        for case in self.cases:
            for phrase in case["must_include"]:
                self.assertFalse(any(token in phrase for token in INTERNAL_EXPECTATION_TOKENS))
            self.assertFalse(any("/" in phrase or "\\" in phrase for phrase in case["must_include"]))

    def test_minimum_case_counts_are_met(self) -> None:
        counts = Counter(case["category"] for case in self.cases)
        self.assertGreaterEqual(len(self.cases), 30)
        minimums = {
            "definition_zh": 8, "translation_en": 6, "pinyin": 2,
            "domain": 1, "alias": 1, "node_boost": 4, "ambiguity": 2,
            "draft_block": 2, "negative_route": 3, "rag_fallback": 1,
        }
        for category, minimum in minimums.items():
            self.assertGreaterEqual(counts[category], minimum)


if __name__ == "__main__":
    unittest.main()
