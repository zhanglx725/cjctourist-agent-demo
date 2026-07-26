"""Pure checks for current-stop glossary context."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import glossary_retrieval


class GlossaryRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        glossary_retrieval.load_glossary.cache_clear()
        glossary_retrieval.load_associations.cache_clear()

    def test_missing_generated_file_degrades_without_inventing_terms(self) -> None:
        with patch.object(glossary_retrieval, "ASSOCIATIONS_FILE", Path("missing.json")):
            self.assertEqual(
                glossary_retrieval.point_glossary_context("label_moon_platform")["status"],
                "associations_not_generated",
            )

    def test_query_match_is_prioritized(self) -> None:
        with patch.object(glossary_retrieval, "load_glossary", return_value={
            "term_openwork": {"term_id": "term_openwork", "zh": "通花", "en": "openwork", "domain": "sculptural_techniques"},
            "term_stone_carving": {"term_id": "term_stone_carving", "zh": "石雕", "en": "stone carving", "domain": "decorative_crafts"},
        }), patch.object(glossary_retrieval, "load_associations", return_value={
            "label_moon_platform": [
                {"term_id": "term_stone_carving", "association_type": "direct_craft_observation"},
                {"term_id": "term_openwork", "association_type": "craft_explanation_context"},
            ]
        }), patch.object(glossary_retrieval, "ASSOCIATIONS_FILE", Path(__file__)):
            result = glossary_retrieval.point_glossary_context("label_moon_platform", "通花栏板是什么")
        self.assertEqual(result["terms"][0]["term_id"], "term_openwork")


if __name__ == "__main__":
    unittest.main()
