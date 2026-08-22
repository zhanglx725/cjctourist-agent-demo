"""Point-to-knowledge profile and optional narration boundary tests."""

from __future__ import annotations

import json
import unittest

from guide_program_planner import plan_stop_program
from guidance_evidence_bundle import build_guidance_evidence_bundle
from narration_coverage import commit_introductions
from point_knowledge_profiles import load_point_knowledge_profiles, optional_context_query
from tour_qa import load_guide_cards


class PointKnowledgeProfileTests(unittest.TestCase):
    def test_every_reviewed_route_stop_has_one_profile(self):
        profiles = load_point_knowledge_profiles()
        route_nodes = set(load_guide_cards())
        self.assertTrue(route_nodes.issubset(profiles))
        for profile in profiles.values():
            self.assertTrue(profile.visible_components)
            self.assertTrue(profile.optional_dimensions)
            self.assertTrue(profile.next_stop_preview)

    def test_front_courtyard_excludes_known_cross_point_gold_toad(self):
        program = plan_stop_program(
            "stop_front_courtyard_center", 900,
            interests=["金蟾吐瑞气"], detail_level="deep",
        )
        self.assertNotIn("金蟾吐瑞气", {item.name for item in program.selected_items})

    def test_optional_query_contains_point_objects_crafts_and_dimensions(self):
        query = optional_context_query(
            "stop_front_courtyard_center",
            "前院中部",
            object_names=("独角狮",),
            crafts=("灰塑",),
        )
        self.assertIn("前院中部", query)
        self.assertIn("独角狮", query)
        self.assertIn("灰塑", query)
        self.assertIn("保护修缮", query)

    def test_optional_context_accepts_related_new_library_and_rejects_unrelated_body_mention(self):
        program = plan_stop_program(
            "stop_front_courtyard_center", 240,
            interests=["独角狮"], detail_level="standard",
        )
        primary = program.selected_items[0]

        def rag(query: str) -> str:
            if "定义 材料 技法" in query:
                evidence = [{
                    "document": "07_ornament_crafts.md", "title_path": [primary.craft],
                    "source_ids": ["S07"], "content": f"{primary.craft}是建筑装饰工艺。",
                }]
            elif primary.ornament_id in query:
                evidence = [{
                    "document": "08_ornament_items.md", "title_path": [primary.name],
                    "source_ids": ["S08"], "content": f"{primary.name}有可核验的造型和故事。",
                }]
            else:
                evidence = [
                    {
                        "document": "11_architectural_conservation.md",
                        "title_path": ["独角狮保护修缮案例"], "source_ids": ["S11"],
                        "content": "馆方2020年资料记载，独角狮腹部裂纹案例使用检测和记录支持修缮判断。",
                    },
                    {
                        "document": "10_people_builders_craftspeople.md",
                        "title_path": ["无关人物"], "source_ids": ["S10"],
                        "content": "这段材料与当前对象、工艺和点位没有关系。",
                    },
                ]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        bundle = build_guidance_evidence_bundle(program, None, rag)
        self.assertIsNotNone(bundle.optional_context)
        documents = {entry["document"] for entry in bundle.optional_context.evidence}
        self.assertEqual(documents, {"11_architectural_conservation.md"})
        dimension = next(
            candidate for candidate in bundle.coverage_candidates
            if candidate.subject_kind == "dimension"
        )
        coverage = commit_introductions(None, [{
            "subject_kind": "dimension",
            "subject_id": dimension.subject_id,
            "source_ids": list(dimension.source_ids),
            "introduced_by": "stop_guidance",
            "node_id": program.node_id,
            "turn_id": "turn:optional:1",
        }])
        repeated = build_guidance_evidence_bundle(program, coverage, rag)
        self.assertEqual(repeated.optional_context.evidence, ())


if __name__ == "__main__":
    unittest.main()
