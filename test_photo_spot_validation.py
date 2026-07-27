"""D5-B tests for editorial photo candidates, not on-site certification."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry, query_registered_cards
from photo_spot_validation import (
    EDITORIAL_ON_SITE_DISCLAIMER,
    photo_spot_availability,
    query_available_photo_spots,
    validate_photo_spot_cards,
)


NODE = "stop_front_courtyard_center"


def _card(card_id: str, card_type: str, *, status: str, raw: dict) -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id, card_type=card_type, runtime_status=status,
        allowed_capabilities=(), allowed_scenarios=(), source_refs=("S11",),
        applicable_node_ids=(NODE,) if card_type == "photo_spot_card" else (), limitations=(),
        raw_payload=raw, visitor_visible=False,
    )


def _valid_fixture(*, pose_status: str = "enabled") -> tuple[dict[str, KnowledgeCard], dict[str, dict]]:
    registry = {
        "photo_ok": _card("photo_ok", "photo_spot_card", status="enabled", raw={
            "photo_spot_id": "photo_ok", "node_id": NODE, "review_status": "draft_manual_review",
            "pose_template_ids": ["pose_ok"], "platform_observation_ids": ["obs_internal"],
            "evidence_refs": ["S11"], "target_ornaments": ["石狮子"],
            "boundaries_zh": "不阻碍通行，不接触构件。", "themes": ["architecture_signature"],
            "title_zh": "前院构图",
        }),
        "pose_ok": _card("pose_ok", "pose_template", status=pose_status, raw={
            "pose_template_id": "pose_ok", "title_zh": "远观细节", "instruction_zh": "站在允许停留处远观。",
            "safety_boundary_zh": "不靠近、不触摸构件。",
        }),
        "obs_internal": _card("obs_internal", "platform_observation", status="disabled", raw={"observation_id": "obs_internal"}),
    }
    eligibility = {"photo_ok": {"runtime_status": "enabled", "location_verification_status": "partial", "safety_verification_status": "pending"}}
    return registry, eligibility


class PhotoSpotValidationTests(unittest.TestCase):
    def test_repository_assets_parse_and_general_queries_never_expose_them(self) -> None:
        cards = build_registry()
        self.assertEqual(len([card for card in cards.values() if card.card_type == "photo_spot_card"]), 12)
        self.assertEqual(len([card for card in cards.values() if card.card_type == "pose_template"]), 8)
        self.assertEqual(len([card for card in cards.values() if card.card_type == "platform_observation"]), 5)
        self.assertFalse({"photo_spot_card", "pose_template", "platform_observation"}.intersection({card.card_type for card in query_registered_cards()}))

    def test_partial_review_can_be_an_editorial_candidate_with_disclaimer(self) -> None:
        registry, eligibility = _valid_fixture()
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: {"石狮子"}},
        )["photo_ok"]
        self.assertTrue(result["available"])
        self.assertEqual(result["availability_tier"], "editorial_candidate")
        self.assertEqual(result["on_site_disclaimer_zh"], EDITORIAL_ON_SITE_DISCLAIMER)

    def test_disabled_pose_or_broken_references_fail_closed(self) -> None:
        registry, eligibility = _valid_fixture(pose_status="disabled")
        registry["photo_ok"].raw_payload.update({"platform_observation_ids": ["missing"], "evidence_refs": ["BAD"]})
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: {"石狮子"}},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertTrue({"disabled_pose_template", "missing_platform_observation", "invalid_evidence_refs"}.issubset(result["reasons"]))

    def test_missing_node_boundary_or_object_mapping_fail_closed(self) -> None:
        registry, eligibility = _valid_fixture()
        registry["photo_ok"].raw_payload.update({"node_id": "not_a_node", "boundaries_zh": "", "target_ornaments": ["不存在装饰"]})
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: {"石狮子"}},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertTrue({"invalid_node_id", "missing_safety_boundary", "unmapped_target_ornament"}.issubset(result["reasons"]))

    def test_specialized_query_returns_only_indirect_poses_and_limitations(self) -> None:
        registry, _ = _valid_fixture()
        verdict = {
            "photo_ok": {"available": True, "node_id": NODE, "pose_template_ids": ("pose_ok",), "limitations": ("不阻碍通行。",)},
        }
        with patch("photo_spot_validation.validate_photo_spot_cards", return_value=verdict), patch("photo_spot_validation.build_registry", return_value=registry):
            result = query_available_photo_spots(node_id=NODE, themes=["architecture_signature"])
        self.assertTrue(result["available"])
        self.assertEqual(result["availability_tier"], "editorial_candidate")
        self.assertEqual(result["pose_templates"][0]["pose_template_id"], "pose_ok")
        self.assertIn(EDITORIAL_ON_SITE_DISCLAIMER, result["limitations"])
        self.assertNotIn("recommended_capture_zh", result["photo_spot"])

    def test_missing_node_does_not_guess_a_photo_position(self) -> None:
        self.assertEqual(query_available_photo_spots(node_id=None), {"available": False, "reason": "missing_node_id"})

    def test_validation_and_query_never_mutate_tour_profile_or_program(self) -> None:
        state = {"tour_state": {"visited_stop_ids": [NODE], "active_stop_program": {"node_id": NODE}}, "visitor_profile": {"interests": ["灰塑"]}}
        before = deepcopy(state)
        validate_photo_spot_cards()
        photo_spot_availability(NODE)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
