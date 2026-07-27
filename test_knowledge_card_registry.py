"""D1 contract tests: registry is read-only and fails closed."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

import knowledge_card_registry as registry
from knowledge_card_contract import stricter_status


class KnowledgeCardRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cards = registry.build_registry()

    def test_all_repository_card_ids_are_unique(self):
        # 82 glossary + 20 research + 8 comparison + 12 photo + 8 pose + 5 platform.
        self.assertEqual(len(self.cards), 135)
        self.assertEqual(len(self.cards), len(set(self.cards)))

    def test_eligibility_manifests_resolve_real_cards(self):
        for manifest, key in ((registry.KNOWLEDGE_ELIGIBILITY, "cards"), (registry.EXPERIENCE_ELIGIBILITY, "records")):
            for card_id in registry._manifest(manifest, key):
                self.assertIn(card_id, self.cards)

    def test_missing_eligibility_defaults_to_disabled(self):
        card = registry._base_card(card_id="missing", card_type="comparison", raw={}, eligibility=None,
                                   source_refs=["x"], nodes=[], limitations=[])
        self.assertEqual(card.runtime_status, "disabled")
        self.assertIn("missing_eligibility", card.validation_errors)

    def test_status_conflict_uses_stricter_value(self):
        self.assertEqual(stricter_status("enabled", "attributed_only"), "attributed_only")
        self.assertEqual(stricter_status("attributed_only", "disabled"), "disabled")

    def test_invalid_nodes_and_sources_cannot_run(self):
        card = registry._base_card(card_id="bad", card_type="research_summary", raw={},
                                   eligibility={"card_type": "research_summary", "runtime_status": "enabled"},
                                   source_refs=[], nodes=["not_a_node"], limitations=[])
        self.assertEqual(card.runtime_status, "disabled")
        self.assertIn("invalid_node_id", card.validation_errors)
        self.assertIn("missing_source_refs", card.validation_errors)

    def test_research_cards_keep_attribution_boundary(self):
        research = [card for card in self.cards.values() if card.card_type == "research_summary"]
        self.assertTrue(research)
        self.assertTrue(all("Must retain research attribution." in card.limitations for card in research))
        self.assertTrue(all(card.runtime_status != "enabled" for card in research))

    def test_draft_english_and_general_comparison_are_closed(self):
        draft = self.cards["term_chitou"]
        self.assertEqual(draft.runtime_status, "disabled")
        self.assertNotIn("en_translation", draft.allowed_capabilities)
        comparisons = [card for card in self.cards.values() if card.card_type == "comparison"]
        self.assertTrue(comparisons)
        self.assertTrue(all("general" not in card.allowed_scenarios for card in comparisons))
        self.assertEqual(registry.query_registered_cards(card_type="comparison", scenario="general"), [])

    def test_experience_assets_are_not_exposed_by_general_visitor_query(self):
        experience = [card for card in self.cards.values() if card.card_type in {"photo_spot_card", "pose_template"}]
        self.assertTrue(experience)
        # Eligibility may mark them as editorial candidates.  They are still
        # unavailable through the generic visitor knowledge-card interface.
        self.assertTrue(all(not card.visitor_visible for card in experience))
        platforms = [card for card in self.cards.values() if card.card_type == "platform_observation"]
        self.assertTrue(platforms)
        self.assertTrue(all(not card.visitor_visible and card.runtime_status == "disabled" for card in platforms))
        returned_types = {card.card_type for card in registry.query_registered_cards()}
        self.assertFalse(returned_types.intersection({"photo_spot_card", "pose_template", "platform_observation"}))

    def test_malformed_file_fails_closed(self):
        with patch.object(registry, "_yaml", return_value={}):
            # Research cards live in individual JSON files and remain
            # discoverable for audit, but absent YAML eligibility makes every
            # surviving record fail closed rather than silently runnable.
            degraded = registry.build_registry()
        self.assertTrue(degraded)
        self.assertTrue(all(card.runtime_status == "disabled" for card in degraded.values()))

    def test_registry_never_mutates_tour_state(self):
        tour_state = {"current_stop_id": "label_moon_platform", "visited_stop_ids": ["x"], "route_status": "touring"}
        before = deepcopy(tour_state)
        registry.build_registry()
        registry.query_registered_cards()
        self.assertEqual(tour_state, before)


if __name__ == "__main__":
    unittest.main()
