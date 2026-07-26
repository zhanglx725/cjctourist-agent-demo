"""Tests for the conservative glossary-to-stop association builder."""

from __future__ import annotations

import json
import unittest

import build_term_stop_associations as builder


class TermStopAssociationTests(unittest.TestCase):
    def test_builder_only_emits_known_terms_and_guide_card_nodes(self) -> None:
        result = builder.build()
        known_terms = builder.glossary_ids()
        cards = json.loads(builder.CARDS_PATH.read_text(encoding="utf-8"))["cards"]
        known_nodes = {card["node_id"] for card in cards}

        self.assertGreater(result["association_count"], 0)
        for item in result["associations"]:
            self.assertIn(item["term_id"], known_terms)
            self.assertIn(item["node_id"], known_nodes)
            self.assertIn(
                item["association_type"],
                {
                    "direct_craft_observation",
                    "craft_explanation_context",
                    "location_component_observation",
                },
            )

    def test_every_card_has_bilingual_glossary_context(self) -> None:
        builder.build()
        cards = json.loads(builder.CARDS_PATH.read_text(encoding="utf-8"))["cards"]
        self.assertTrue(all(card["glossary_ids"] for card in cards))


if __name__ == "__main__":
    unittest.main()
