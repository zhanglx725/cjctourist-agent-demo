"""Build conservative glossary-to-stop associations from approved guide cards.

This script does not infer an ornament's physical location.  It only uses the
already reviewed ornament mapping embedded in node_guide_cards_v1.json and
adds glossary terms that explain the crafts or clearly named components at a
guide stop.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).parent
GLOSSARY_PATH = ROOT / "data" / "chen_clan_academy" / "glossary" / "glossary_zh_en_v0.yaml"
CARDS_PATH = ROOT / "data" / "chen_clan_academy" / "routes" / "node_guide_cards_v1.json"
OUTPUT_PATH = ROOT / "data" / "chen_clan_academy" / "routes" / "term_stop_associations_v1.json"

# Every mapping is grounded in a craft explicitly recorded in the approved
# ornament mapping.  The first ID names the craft; the remaining IDs provide
# safe material/process context at the same stop.
CRAFT_TERMS: dict[str, list[str]] = {
    "灰塑": [
        "term_lime_plaster_relief",
        "term_lime",
        "term_straw_fiber_lime_mortar",
        "term_paper_fiber_lime_mortar",
    ],
    "陶塑": [
        "term_ceramic_sculpture",
        "term_shiwan_ceramic_ridge",
        "term_ceramic_clay",
        "term_colored_glaze",
        "term_applique_modeling",
        "term_hand_modeling",
        "term_mold_making",
    ],
    "木雕": [
        "term_wood_carving",
        "term_relief_carving",
        "term_openwork_carving",
    ],
    "石雕": [
        "term_stone_carving",
        "term_granite",
        "term_carving_in_the_round",
    ],
    "砖雕": [
        "term_brick_carving",
        "term_blue_brick",
        "term_water_polished_blue_brick",
        "term_incised_carving",
        "term_high_relief",
        "term_low_relief",
        "term_pierced_carving",
    ],
    "铜铁铸": [
        "term_cast_copper_and_iron",
        "term_openwork",
    ],
    "彩绘": ["term_painted_decoration"],
}

# A component is associated only when it is named in a reviewed ornament's
# location description.  These terms supplement, but never replace, craft
# evidence.
LOCATION_COMPONENT_TERMS: dict[str, str] = {
    "屋脊": "term_roof_ridge",
    "山墙": "term_gable_wall",
    "屏门": "term_screen_door",
    "屏风": "term_screen",
    "神龛": "term_shrine_niche",
    "栏杆": "term_balustrade",
    "栏板": "term_railing_panel",
    "连廊": "term_eaves_corridor",
    "檐廊": "term_eaves_corridor",
}


def glossary_ids() -> set[str]:
    text = GLOSSARY_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"^  - term_id: ([a-z0-9_]+)$", text, re.MULTILINE))


def craft_matches(craft: str) -> list[str]:
    return [name for name in CRAFT_TERMS if name in craft]


def add_association(
    bucket: dict[tuple[str, str], dict],
    *,
    node_id: str,
    term_id: str,
    association_type: str,
    evidence: str,
) -> None:
    key = (node_id, term_id)
    previous = bucket.get(key)
    if previous is None or association_type == "direct_craft_observation":
        bucket[key] = {
            "node_id": node_id,
            "term_id": term_id,
            "association_type": association_type,
            "status": "derived_from_approved_ornament_mapping",
            "evidence": evidence,
        }


def build() -> dict:
    known_terms = glossary_ids()
    payload = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    associations: dict[tuple[str, str], dict] = {}

    for card in payload["cards"]:
        node_id = card["node_id"]
        for ornament in card.get("ornaments", []):
            craft = ornament.get("craft", "")
            evidence = f"{ornament['ornament_id']} ({ornament['name']} / {craft})"
            for craft_name in craft_matches(craft):
                term_ids = CRAFT_TERMS[craft_name]
                add_association(
                    associations,
                    node_id=node_id,
                    term_id=term_ids[0],
                    association_type="direct_craft_observation",
                    evidence=evidence,
                )
                for term_id in term_ids[1:]:
                    add_association(
                        associations,
                        node_id=node_id,
                        term_id=term_id,
                        association_type="craft_explanation_context",
                        evidence=evidence,
                    )

            location = ornament.get("raw_location", "")
            for keyword, term_id in LOCATION_COMPONENT_TERMS.items():
                if keyword in location:
                    add_association(
                        associations,
                        node_id=node_id,
                        term_id=term_id,
                        association_type="location_component_observation",
                        evidence=f"{evidence}; 原始位置含“{keyword}”",
                    )

    unknown = {item["term_id"] for item in associations.values()} - known_terms
    if unknown:
        raise ValueError(f"关联了不存在的术语 ID: {sorted(unknown)}")

    by_stop: dict[str, list[str]] = defaultdict(list)
    for item in associations.values():
        by_stop[item["node_id"]].append(item["term_id"])
    for card in payload["cards"]:
        # glossary_ids is the existing extension point for bilingual terms.
        card["glossary_ids"] = sorted(set(by_stop[card["node_id"]]))

    result = {
        "schema_version": "v1",
        "generation_policy": {
            "source": "approved node guide cards and reviewed ornament-to-node mapping",
            "boundary": "Only craft and explicitly named component context are associated; general historical terms remain global unless separately reviewed.",
        },
        "association_count": len(associations),
        "associations": sorted(
            associations.values(), key=lambda item: (item["node_id"], item["term_id"])
        ),
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CARDS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    generated = build()
    print(f"Generated {generated['association_count']} term-stop associations: {OUTPUT_PATH}")
