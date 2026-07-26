"""Audit checks for standalone card-runtime eligibility metadata."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parent
DATA_ROOT = ROOT / "data" / "chen_clan_academy"
ELIGIBILITY_FILE = DATA_ROOT / "card_runtime_eligibility_knowledge_v1.yaml"


class CardRuntimeEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.eligibility = yaml.safe_load(ELIGIBILITY_FILE.read_text(encoding="utf-8"))
        cls.records = cls.eligibility["cards"]
        cls.by_id = {record["card_id"]: record for record in cls.records}

        glossary = yaml.safe_load((DATA_ROOT / "glossary" / "glossary_zh_en_v0.yaml").read_text(encoding="utf-8"))
        cls.terms = {term["term_id"]: term for term in glossary["terms"]}
        cls.research = {
            card["card_id"]: card
            for path in (DATA_ROOT / "research_cards").glob("research_*.json")
            if path.name not in {"research_sources_v1.json", "research_card_review_index_v1.json"}
            for card in [json.loads(path.read_text(encoding="utf-8"))]
        }
        comparisons = yaml.safe_load((DATA_ROOT / "comparisons" / "comparison_cards_v0.yaml").read_text(encoding="utf-8"))
        cls.comparisons = {card["comparison_id"]: card for card in comparisons["cards"]}
        cls.target_ids = set(cls.terms) | set(cls.research) | set(cls.comparisons)
        registry_text = (DATA_ROOT / "sources" / "source_registry.md").read_text(encoding="utf-8")
        cls.registered_term_sources = set(re.findall(r"\bS\d+\b", registry_text))

    def test_manifest_covers_exactly_all_110_target_cards(self) -> None:
        self.assertEqual(len(self.target_ids), 110)
        self.assertEqual(len(self.records), 110)
        self.assertEqual(set(self.by_id), self.target_ids)

    def test_card_ids_are_unique_and_resolve_to_real_cards(self) -> None:
        self.assertEqual(len(self.records), len(self.by_id))
        self.assertTrue(set(self.by_id).issubset(self.target_ids))

    def test_controlled_enums_and_required_audit_fields(self) -> None:
        controlled = self.eligibility["controlled_values"]
        for record in self.records:
            self.assertIn(record["card_type"], controlled["card_type"])
            self.assertIn(record["runtime_status"], controlled["runtime_status"])
            self.assertIn(record["fact_verification_status"], controlled["fact_verification_status"])
            self.assertIsInstance(record["allowed_capabilities"], list)
            self.assertIsInstance(record["allowed_scenarios"], list)
            self.assertIsInstance(record["limitations"], list)
            self.assertIn("reviewer", record)
            self.assertIn("reviewed_at", record)

    def test_enabled_cards_have_valid_registered_sources(self) -> None:
        for record in self.records:
            if record["runtime_status"] != "enabled":
                continue
            self.assertEqual(record["card_type"], "glossary_term")
            term = self.terms[record["card_id"]]
            self.assertTrue(term["source_ids"])
            self.assertTrue(set(term["source_ids"]).issubset(self.registered_term_sources))

    def test_draft_translations_cannot_gain_english_output_capability(self) -> None:
        for term_id, term in self.terms.items():
            record = self.by_id[term_id]
            if term["translation_status"] == "draft":
                self.assertEqual(record["runtime_status"], "disabled")
                self.assertNotIn("en_translation", record["allowed_capabilities"])

    def test_background_research_cards_cannot_be_enabled(self) -> None:
        for card_id, card in self.research.items():
            if card["status"] == "background":
                self.assertEqual(self.by_id[card_id]["runtime_status"], "disabled")

    def test_comparisons_cannot_enter_general_visitor_mode(self) -> None:
        for card_id in self.comparisons:
            record = self.by_id[card_id]
            self.assertEqual(record["runtime_status"], "attributed_only")
            self.assertNotIn("general", record["allowed_scenarios"])
            self.assertEqual(
                record["allowed_scenarios"],
                ["study", "professional", "explicit_research_comparison"],
            )

    def test_partial_or_pending_cards_never_become_unconditional_facts(self) -> None:
        for record in self.records:
            if record["fact_verification_status"] != "verified":
                self.assertNotEqual(record["runtime_status"], "enabled")
                self.assertNotIn("unconditional_fact", record["allowed_capabilities"])

    def test_missing_eligibility_record_defaults_to_disabled(self) -> None:
        def runtime_status_for(card_id: str) -> str:
            return self.by_id.get(card_id, {}).get(
                "runtime_status",
                self.eligibility["default_runtime_status_for_missing_record"],
            )

        self.assertEqual(runtime_status_for("unknown_card_id"), "disabled")
        self.assertEqual(runtime_status_for("missing_card_id"), "disabled")


if __name__ == "__main__":
    unittest.main()


