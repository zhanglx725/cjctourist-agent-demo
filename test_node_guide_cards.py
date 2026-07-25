import unittest

from build_node_guide_cards import build_cards, read_csv, CATALOG_FILE, MAPPING_FILE


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

    def test_every_card_reserves_empty_extension_interfaces(self):
        card = self.by_id["label_moon_platform"]
        extensions = card["extensions"]
        self.assertEqual(extensions["research_summary_card_ids"], [])
        self.assertEqual(extensions["comparison_card_ids"], [])
        self.assertEqual(extensions["term_card_ids"], [])
        self.assertEqual(extensions["photo_spot_card_ids"], [])
        self.assertEqual(extensions["route_effect"]["photo_spot"], "disabled_until_reviewed")


if __name__ == "__main__":
    unittest.main()
