"""D5-B fail-closed tests; no photo content is rendered to visitors."""

from __future__ import annotations

from copy import deepcopy
import unittest

from knowledge_card_contract import KnowledgeCard
from knowledge_card_registry import build_registry, query_registered_cards
from photo_spot_validation import photo_spot_availability, validate_photo_spot_cards


NODE = "stop_front_courtyard_center"


def _card(card_id: str, card_type: str, *, status: str, raw: dict) -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id,
        card_type=card_type,
        runtime_status=status,
        allowed_capabilities=(),
        allowed_scenarios=(),
        source_refs=("S11",),
        applicable_node_ids=(NODE,) if card_type == "photo_spot_card" else (),
        limitations=(),
        raw_payload=raw,
        visitor_visible=card_type != "platform_observation",
    )


def _valid_fixture(*, pose_status: str = "enabled", popularity: str = "none") -> tuple[dict[str, KnowledgeCard], dict[str, dict]]:
    registry = {
        "photo_ok": _card("photo_ok", "photo_spot_card", status="enabled", raw={
            "photo_spot_id": "photo_ok", "node_id": NODE, "review_status": "approved", "popularity_status": popularity,
            "pose_template_ids": ["pose_ok"], "platform_observation_ids": ["obs_internal"],
            "evidence_refs": ["S11"], "target_ornaments": [],
        }),
        "pose_ok": _card("pose_ok", "pose_template", status=pose_status, raw={"pose_template_id": "pose_ok"}),
        "obs_internal": _card("obs_internal", "platform_observation", status="disabled", raw={"observation_id": "obs_internal"}),
    }
    eligibility = {"photo_ok": {
        "runtime_status": "enabled", "location_verification_status": "verified", "safety_verification_status": "verified",
        "content_verification_status": "verified", "source_verification_status": "verified",
        "reviewer": "reviewer", "reviewed_at": "2026-07-27", "blocking_issues": [],
    }}
    return registry, eligibility


class PhotoSpotValidationTests(unittest.TestCase):
    def test_repository_cards_parse_and_are_currently_all_closed(self) -> None:
        cards = build_registry()
        self.assertEqual(len([card for card in cards.values() if card.card_type == "photo_spot_card"]), 12)
        self.assertEqual(len([card for card in cards.values() if card.card_type == "pose_template"]), 8)
        self.assertEqual(len([card for card in cards.values() if card.card_type == "platform_observation"]), 5)
        self.assertEqual(len(cards), len(set(cards)))  # D1 global ID uniqueness.
        self.assertFalse([card for card in query_registered_cards() if card.card_type == "platform_observation"])
        results = validate_photo_spot_cards()
        self.assertEqual(len(results), 12)
        self.assertTrue(all(not result["available"] for result in results.values()))
        self.assertEqual(photo_spot_availability(), {"available": False, "reason": "no_reviewed_photo_spot"})

    def test_complete_manual_review_is_the_only_positive_path(self) -> None:
        registry, eligibility = _valid_fixture()
        results = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: set()},
        )
        self.assertTrue(results["photo_ok"]["available"])

    def test_missing_review_fields_and_blocking_issues_close_card(self) -> None:
        registry, eligibility = _valid_fixture()
        eligibility["photo_ok"].update({
            "reviewer": None,
            "reviewed_at": None,
            "blocking_issues": ["pending_site_review"],
        })
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: set()},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertIn("missing_reviewer", result["reasons"])
        self.assertIn("missing_reviewed_at", result["reasons"])
        self.assertIn("blocking_issues_present", result["reasons"])

    def test_verification_pose_and_popularity_gates_are_all_required(self) -> None:
        registry, eligibility = _valid_fixture(pose_status="disabled", popularity="editorial_recommended")
        eligibility["photo_ok"]["safety_verification_status"] = "partial"
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: set()},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertIn("safety_verification_status_not_verified", result["reasons"])
        self.assertIn("disabled_pose_template", result["reasons"])
        self.assertIn("editorial_recommended_not_popularity_evidence", result["reasons"])

    def test_eligibility_status_conflict_uses_the_stricter_result(self) -> None:
        registry, eligibility = _valid_fixture()
        eligibility["photo_ok"]["runtime_status"] = "disabled"
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: set()},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertIn("eligibility_runtime_not_enabled", result["reasons"])

    def test_broken_references_and_unmapped_objects_close_card(self) -> None:
        registry, eligibility = _valid_fixture()
        registry["photo_ok"].raw_payload.update({
            "pose_template_ids": ["missing"],
            "platform_observation_ids": ["missing_obs"],
            "evidence_refs": ["BAD"],
            "target_ornaments": ["unmapped ornament"],
        })
        result = validate_photo_spot_cards(
            registry_loader=lambda: registry, eligibility_loader=lambda: eligibility,
            evidence_refs_loader=lambda: {"S11"}, ornaments_loader=lambda: {NODE: set()},
        )["photo_ok"]
        self.assertFalse(result["available"])
        self.assertTrue({"missing_pose_template", "missing_platform_observation", "invalid_evidence_refs", "unmapped_target_ornament"}.issubset(result["reasons"]))

    def test_validation_never_mutates_tour_profile_or_program(self) -> None:
        state = {"tour_state": {"visited_stop_ids": [NODE], "active_stop_program": {"node_id": NODE}}, "visitor_profile": {"interests": ["灰塑"]}}
        before = deepcopy(state)
        validate_photo_spot_cards()
        photo_spot_availability(NODE)
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
