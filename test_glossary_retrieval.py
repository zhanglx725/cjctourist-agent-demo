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

    def test_current_node_scope_returns_only_direct_local_object_mappings(self) -> None:
        instances = glossary_retrieval.reviewed_term_instances(
            "term_lime_plaster_relief",
            current_node_id="stop_front_courtyard_center",
            scope="current_node",
        )
        self.assertGreaterEqual(len(instances), 1)
        self.assertLessEqual(len(instances), 2)
        self.assertEqual(instances[0]["node_id"], "stop_front_courtyard_center")
        self.assertEqual(instances[0]["ornament_id"], "orn_022")
        self.assertEqual(instances[0]["ornament_name"], "松鹤延年")
        self.assertEqual(instances[0]["craft"], "灰塑")
        self.assertEqual(instances[0]["association_type"], "direct_craft_observation")
        self.assertTrue(all(item["node_id"] == "stop_front_courtyard_center" for item in instances))

    def test_whole_site_scope_is_stable_and_current_scope_never_pads(self) -> None:
        current = glossary_retrieval.reviewed_term_instances(
            "term_stone_carving",
            current_node_id="label_moon_platform",
            scope="current_node",
        )
        whole_site = glossary_retrieval.reviewed_term_instances(
            "term_stone_carving", scope="whole_site"
        )
        self.assertEqual([item["ornament_id"] for item in current], ["orn_078"])
        self.assertEqual(whole_site[:2], sorted(
            whole_site[:2], key=lambda item: (item["node_id"], item["ornament_id"])
        ))
        self.assertTrue(all(item["node_id"] == "label_moon_platform" for item in current))

    def test_context_only_association_is_not_promoted_to_an_object_instance(self) -> None:
        instances = glossary_retrieval.reviewed_term_instances(
            "term_openwork",
            current_node_id="label_moon_platform",
            scope="current_node",
        )
        self.assertEqual(instances, [])


if __name__ == "__main__":
    unittest.main()
