import json
import unittest

from build_node_guide_cards import (
    CATALOG_FILE,
    MAPPING_FILE,
    OUTPUT_FILE,
    build_cards,
    read_csv,
)


class NodeGuideCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_cards(read_csv(CATALOG_FILE), read_csv(MAPPING_FILE))
        cls.by_id = {card["node_id"]: card for card in cls.result["cards"]}

    def test_every_approved_route_stop_has_a_card(self):
        self.assertEqual(self.result["card_count"], 12)

    def test_moon_platform_card_keeps_all_mapped_ornaments(self):
        moon = self.by_id["label_moon_platform"]
        self.assertEqual(moon["ornament_count"], 10)
        self.assertIn("杏林春燕", [item["name"] for item in moon["ornaments"]])

    def test_cards_instruct_agent_to_use_rag_for_final_facts(self):
        card = self.by_id["stop_front_courtyard_center"]
        self.assertIn("RAG", card["evidence_rules"]["answer_rule"])

    def test_reviewed_research_cards_are_attached_only_to_selected_nodes(self):
        card = self.by_id["label_moon_platform"]
        extensions = card["extensions"]
        self.assertEqual(
            extensions["research_summary_card_ids"],
            [
                "research_004_spatial_characteristics",
                "research_006_sculptural_metaphor",
                "research_015_grid_spatial_layout",
                "research_016_academy_ancestral_program",
                "research_018_woodcarving_screens_and_shrines",
                "research_019_stone_platform_and_railings",
            ],
        )
        self.assertEqual(extensions["route_effect"]["research_summary"], "available")
        self.assertEqual(extensions["comparison_card_ids"], [])
        self.assertEqual(extensions["term_card_ids"], [])
        self.assertEqual(extensions["photo_spot_card_ids"], [])
        self.assertEqual(extensions["route_effect"]["photo_spot"], "disabled_until_reviewed")

    def test_unmapped_nodes_keep_research_interface_empty(self):
        card = self.by_id["stop_front_east_courtyard"]
        self.assertEqual(card["extensions"]["research_summary_card_ids"], [])
        self.assertEqual(card["extensions"]["route_effect"]["research_summary"], "none")

    def test_cards_keep_mapping_audit_fields_for_location_hints(self):
        item = self.by_id["label_moon_platform"]["ornaments"][0]
        self.assertEqual(item["final_node_id"], "label_moon_platform")
        self.assertIn(item["mapping_decision"], {"change", "add_node"})
        self.assertTrue(item["mapping_source"].startswith("manual_review_"))

    def test_committed_cards_match_a_fresh_build_from_reviewed_inputs(self):
        """Keep route-selection evidence fresh without comparing later card enrichments.

        ``build_term_stop_associations.py`` deliberately appends ``glossary_ids``
        after the base node-card build.  Route selection does not read that
        extension, so this test compares only its reviewed object evidence and
        its derived statistics.
        """
        committed = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        fresh = build_cards(read_csv(CATALOG_FILE), read_csv(MAPPING_FILE))

        committed_by_id = {card["node_id"]: card for card in committed["cards"]}
        fresh_by_id = {card["node_id"]: card for card in fresh["cards"]}
        self.assertEqual(set(committed_by_id), set(fresh_by_id))

        for node_id in sorted(fresh_by_id):
            committed_card = committed_by_id[node_id]
            fresh_card = fresh_by_id[node_id]
            self.assertEqual(
                self._route_selection_projection(committed_card),
                self._route_selection_projection(fresh_card),
                node_id,
            )

    def _route_selection_projection(self, card):
        node_id = card["node_id"]
        ornaments = sorted(
            (
                {
                    "ornament_id": ornament["ornament_id"],
                    "name": ornament["name"],
                    "craft": ornament["craft"],
                    "final_node_id": ornament["final_node_id"],
                    "mapping_decision": ornament["mapping_decision"],
                    "mapping_source": ornament["mapping_source"],
                }
                for ornament in card["ornaments"]
            ),
            key=lambda ornament: ornament["ornament_id"],
        )

        self.assertEqual(card["ornament_count"], len(ornaments), node_id)
        self.assertTrue(
            all(ornament["final_node_id"] == node_id for ornament in ornaments),
            node_id,
        )
        self.assertTrue(
            all(ornament["mapping_decision"] in {"change", "add_node"} for ornament in ornaments),
            node_id,
        )

        expected_crafts = {}
        for ornament in ornaments:
            expected_crafts[ornament["craft"]] = expected_crafts.get(ornament["craft"], 0) + 1
        self.assertEqual(card["craft_distribution"], dict(sorted(expected_crafts.items())), node_id)

        return {
            "ornaments": ornaments,
            "ornament_count": card["ornament_count"],
            "craft_distribution": card["craft_distribution"],
        }


if __name__ == "__main__":
    unittest.main()
