"""Build structured guide-card context for approved ornament-rich route stops."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ROUTES_DIR = ROOT / "data" / "chen_clan_academy" / "routes"
SPATIAL_DIR = ROOT / "data" / "chen_clan_academy" / "spatial"
CATALOG_FILE = ROUTES_DIR / "route_stop_catalog_v1.csv"
MAPPING_FILE = SPATIAL_DIR / "ornament_spatial_mapping_v1.csv"
RESEARCH_CARD_MAPPING_FILE = ROUTES_DIR / "research_card_node_mapping_v1.json"
OUTPUT_FILE = ROUTES_DIR / "node_guide_cards_v1.json"

# The importer writes only human-reviewed rows. Keep this guard so a
# hand-edited/stale mapping cannot silently become a guide-card association.
REVIEWED_MAPPING_DECISIONS = {"change", "add_node"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_research_card_mappings(path: Path = RESEARCH_CARD_MAPPING_FILE) -> dict[str, list[str]]:
    """Read manually reviewed research-card associations by route-stop ID."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["node_id"]: item["research_summary_card_ids"]
        for item in data["node_mappings"]
    }


def build_cards(
    catalog_rows: list[dict[str, str]],
    mapping_rows: list[dict[str, str]],
    research_card_mappings: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    research_card_mappings = research_card_mappings or read_research_card_mappings()
    by_node: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in mapping_rows:
        if (
            item.get("final_node_id")
            and item.get("mapping_decision") in REVIEWED_MAPPING_DECISIONS
        ):
            by_node[item["final_node_id"]].append(item)

    cards: list[dict[str, object]] = []
    for stop in catalog_rows:
        if stop["review_status"] != "approved" or stop["route_eligible"] != "true":
            continue
        ornaments = sorted(by_node[stop["node_id"]], key=lambda item: item["ornament_id"])
        craft_counts = Counter(item["craft"] for item in ornaments)
        research_card_ids = research_card_mappings.get(stop["node_id"], [])
        cards.append(
            {
                "node_id": stop["node_id"],
                "display_name": stop["stop_name"],
                "route_role": stop["route_role"],
                "recommended_visit_minutes": int(stop["recommended_visit_minutes"]),
                "themes": stop["themes"].split(";"),
                "guide_focus": stop["guide_focus"],
                "ornament_count": len(ornaments),
                "craft_distribution": dict(sorted(craft_counts.items())),
                "ornaments": [
                    {
                        "ornament_id": item["ornament_id"],
                        "name": item["ornament_name"],
                        "craft": item["craft"],
                        "raw_location": item["raw_location"],
                        "final_node_id": item["final_node_id"],
                        "mapping_decision": item["mapping_decision"],
                        "mapping_source": item["mapping_source"],
                    }
                    for item in ornaments
                ],
                "rag_queries": [
                    f"{stop['stop_name']} {stop['guide_focus']}",
                    *[f"{item['ornament_name']} 是什么装饰" for item in ornaments],
                ],
                "extensions": {
                    "research_summary_card_ids": research_card_ids,
                    "comparison_card_ids": [],
                    "term_card_ids": [],
                    "photo_spot_card_ids": [],
                    "glossary_ids": [],
                    "route_effect": {
                        "research_summary": "available" if research_card_ids else "none",
                        "comparison": "none",
                        "term": "none",
                        "glossary": "none",
                        "photo_spot": "disabled_until_reviewed"
                    }
                },
                "evidence_rules": {
                    "item_detail": "08_ornament_items.md",
                    "item_location": "09_ornament_locations.md",
                    "craft_context": "07_ornament_crafts.md",
                    "answer_rule": "最终事实讲解必须经现有 RAG 取证，不直接把本卡片当作事实正文。",
                    "extension_rule": "扩展卡必须先建立独立、可追溯的数据源，再按 card_id 关联；空数组表示当前没有可用内容。",
                },
            }
        )
    return {
        "schema_version": "v1",
        "source": {
            "catalog": str(CATALOG_FILE.relative_to(ROOT)).replace("\\", "/"),
            "ornament_mapping": str(MAPPING_FILE.relative_to(ROOT)).replace("\\", "/"),
            "research_card_mapping": str(RESEARCH_CARD_MAPPING_FILE.relative_to(ROOT)).replace("\\", "/"),
        },
        "card_count": len(cards),
        "cards": cards,
    }


def main() -> None:
    result = build_cards(read_csv(CATALOG_FILE), read_csv(MAPPING_FILE))
    OUTPUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已生成 {result['card_count']} 个点位讲解包：{OUTPUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
