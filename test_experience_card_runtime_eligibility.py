"""Closed-gate checks for photo spots, pose templates, and platform observations."""

from __future__ import annotations

import csv
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import yaml

import experience_card_runtime_gate as gate


ROOT = Path(__file__).parent
DATA = ROOT / "data" / "chen_clan_academy"
PHOTO_FILE = DATA / "photo_spots" / "photo_spot_cards_v0.yaml"
POSE_FILE = DATA / "photo_spots" / "pose_templates_v0.yaml"
PLATFORM_FILE = DATA / "photo_spots" / "platform_observations_v0.yaml"
ELIGIBILITY_FILE = DATA / "card_runtime_eligibility_experience_v1.yaml"
MARKERS_FILE = DATA / "spatial" / "marker_inventory_v0.csv"
ORNAMENT_MAPPING_FILE = DATA / "spatial" / "ornament_spatial_mapping_v1.csv"
SOURCE_REGISTRY_FILE = DATA / "sources" / "source_registry.md"
COMPARISON_EVIDENCE_FILE = DATA / "comparisons" / "comparison_evidence_notes_v0.md"


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


class ExperienceCardRuntimeEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.photos = load_yaml(PHOTO_FILE)["cards"]
        cls.poses = load_yaml(POSE_FILE)["templates"]
        cls.observations = load_yaml(PLATFORM_FILE)["observations"]
        cls.manifest = load_yaml(ELIGIBILITY_FILE)
        cls.records = cls.manifest["records"]
        with MARKERS_FILE.open(encoding="utf-8-sig") as handle:
            cls.markers = list(csv.DictReader(handle))
        with ORNAMENT_MAPPING_FILE.open(encoding="utf-8-sig") as handle:
            cls.ornaments = list(csv.DictReader(handle))

    def test_all_data_files_parse_and_expected_inventory_is_complete(self) -> None:
        self.assertEqual(len(self.photos), 12)
        self.assertEqual(len(self.poses), 8)
        self.assertEqual(len(self.observations), 5)
        self.assertEqual(len(self.records), 25)

    def test_source_and_eligibility_ids_are_unique_and_exactly_covered(self) -> None:
        groups = [
            (self.photos, "photo_spot_id"),
            (self.poses, "pose_template_id"),
            (self.observations, "observation_id"),
            (self.records, "card_id"),
        ]
        for items, field in groups:
            ids = [item[field] for item in items]
            self.assertEqual(len(ids), len(set(ids)), field)

        source_ids = {
            *(item["photo_spot_id"] for item in self.photos),
            *(item["pose_template_id"] for item in self.poses),
            *(item["observation_id"] for item in self.observations),
        }
        self.assertEqual(source_ids, {item["card_id"] for item in self.records})

    def test_eligibility_records_have_required_closed_gate_fields(self) -> None:
        required = {
            "card_id",
            "card_type",
            "runtime_status",
            "location_verification_status",
            "safety_verification_status",
            "allowed_scenarios",
            "reviewer",
            "reviewed_at",
            "limitations",
        }
        for record in self.records:
            self.assertTrue(required <= set(record), record["card_id"])
            self.assertIn(record["runtime_status"], {"enabled", "attributed_only", "disabled"})
            self.assertIn(record["location_verification_status"], {"verified", "partial", "pending"})
            self.assertIn(record["safety_verification_status"], {"verified", "partial", "pending"})
            self.assertIsInstance(record["allowed_scenarios"], list)
            self.assertIsInstance(record["limitations"], list)

    def test_default_approved_photo_cards_are_enabled_but_platform_observations_stay_disabled(self) -> None:
        records = {item["card_id"]: item for item in self.records}
        self.assertTrue(all(records[item["photo_spot_id"]]["runtime_status"] == "enabled" for item in self.photos))
        self.assertTrue(all(records[item["observation_id"]]["runtime_status"] == "disabled" for item in self.observations))

    def test_default_approval_overrides_pose_runtime_but_preserves_source_warning(self) -> None:
        records = {item["card_id"]: item for item in self.records}
        disabled = {
            item["pose_template_id"]
            for item in self.poses
            if item.get("trend_status") == "disabled_until_visual_review"
        }
        self.assertEqual(disabled, {"pose_ornament_reference_pending"})
        self.assertTrue(all(records[pose_id]["runtime_status"] == "enabled" for pose_id in disabled))
        self.assertEqual(
            next(item for item in self.poses if item["pose_template_id"] in disabled)["trend_status"],
            "disabled_until_visual_review",
        )
        self.assertEqual(len(gate.select_pose_templates()["cards"]), 8)

    def test_photo_references_and_marker_node_ids_are_valid(self) -> None:
        node_ids = {item["node_id"] for item in self.markers if item.get("status") == "confirmed_from_map"}
        pose_ids = {item["pose_template_id"] for item in self.poses}
        observation_ids = {item["observation_id"] for item in self.observations}
        for card in self.photos:
            self.assertIn(card["node_id"], node_ids, card["photo_spot_id"])
            self.assertFalse(set(card["pose_template_ids"]) - pose_ids, card["photo_spot_id"])
            self.assertFalse(set(card.get("platform_observation_ids", [])) - observation_ids, card["photo_spot_id"])

    def test_photo_evidence_references_are_registered(self) -> None:
        registry = SOURCE_REGISTRY_FILE.read_text(encoding="utf-8")
        comparison_evidence = COMPARISON_EVIDENCE_FILE.read_text(encoding="utf-8")
        for card in self.photos:
            for source_id in card["evidence_refs"]:
                registered = f"| {source_id} |" in registry or source_id in comparison_evidence
                self.assertTrue(registered, card["photo_spot_id"])

    def test_unmapped_or_category_targets_are_explicitly_limited(self) -> None:
        mapped_names = {item["ornament_name"] for item in self.ornaments}
        records = {item["card_id"]: item for item in self.records}
        missing = defaultdict(list)
        for card in self.photos:
            for target in card["target_ornaments"]:
                if target not in mapped_names:
                    missing[card["photo_spot_id"]].append(target)

        self.assertEqual(
            dict(missing),
            {
                "photo_architecture_roof_ridge": ["瓜瓞绵绵"],
                "photo_craft_ornament_route": ["灰塑", "木雕", "石雕", "陶塑"],
                "photo_juxian_hall_screen_door": ["木雕屏门"],
            },
        )
        for card_id, targets in missing.items():
            limitations = " ".join(records[card_id]["limitations"])
            for target in targets:
                self.assertIn(target, limitations, card_id)

    def test_duplicate_ornament_names_are_known_audit_risk_not_auto_resolved(self) -> None:
        names = Counter(item["ornament_name"] for item in self.ornaments)
        duplicates = {name for name, count in names.items() if count > 1}
        self.assertTrue({"福", "踏雪寻梅", "太平有象"} <= duplicates)

    def test_default_approved_photo_card_can_be_selected(self) -> None:
        gate.load_eligibility_records.cache_clear()
        result = gate.select_photo_spot_cards("label_moon_platform")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["message_zh"], "")
        self.assertEqual([item["photo_spot_id"] for item in result["cards"]], ["photo_architecture_moon_platform"])

    def test_platform_observations_cannot_output(self) -> None:
        result = gate.select_platform_observations()
        self.assertEqual(result["status"], "no_approved_content")
        self.assertEqual(result["cards"], [])

    def test_missing_eligibility_record_fails_closed(self) -> None:
        with patch.object(gate, "load_eligibility_records", return_value={}):
            result = gate.select_photo_spot_cards("label_moon_platform")
        self.assertEqual(result["status"], "no_approved_content")
        self.assertEqual(result["message_zh"], "暂无审核通过内容")
        self.assertEqual(result["cards"], [])


if __name__ == "__main__":
    unittest.main()
