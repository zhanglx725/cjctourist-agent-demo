"""Offline E5-A3 tests for evidence-only neutral narration rendering."""

from __future__ import annotations

from dataclasses import replace
import json
import unittest

from guidance_evidence_bundle import build_guidance_evidence_bundle
from guidance_policy import build_guidance_policy
from guide_program_planner import plan_stop_program
from narration_coverage import commit_introductions
from narration_rendering import render_guidance_evidence
from visitor_profile import create_visitor_profile


def _entry(document: str, title: str, source: str, content: str) -> dict:
    return {"document": document, "title_path": ["知识库", title], "source_ids": [source], "content": content}


class NarrationRenderingTests(unittest.TestCase):
    def setUp(self):
        self.program = plan_stop_program("stop_front_courtyard_center", 240, interests=["灰塑"], detail_level="standard")
        self.primary = self.program.selected_items[0]
        self.second = self.program.selected_items[1]

    def _bundle(self, program=None, *, coverage=None, no_craft: bool = False, no_ornaments: bool = False, wrong_primary: bool = False):
        program = program or self.program
        def rag(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                craft = next(item.craft for item in program.selected_items if query.startswith(item.craft))
                evidence = [] if no_craft else [_entry("07_ornament_crafts.md", craft, "S07", f"{craft}是岭南传统建筑装饰工艺，常见于山墙和屋脊。制作时可用石灰等材料堆塑，形成有层次的造型。")]
            else:
                item = next(candidate for candidate in program.selected_items if candidate.name in query)
                title = "福禄寿" if wrong_primary and item.ornament_id == self.primary.ornament_id else item.name
                content = (
                    f"{title}全身朱红色，独角，造型凌空而下。这个题材源自民间传说，寓意辟邪保平安。"
                    if item.ornament_id == self.primary.ornament_id
                    else f"{title}的构图呈现鲜明的造型层次。这个题材寄托对美好生活的祈盼。"
                )
                evidence = [] if no_ornaments else [_entry(
                    "08_ornament_items.md", title, "S08",
                    content,
                )]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)
        return build_guidance_evidence_bundle(program, coverage, rag)

    def test_first_craft_precedes_object_and_is_not_repeated(self):
        result = render_guidance_evidence(self.program, self._bundle())
        self.assertIn("先认识灰塑", result.visitor_message)
        self.assertLess(result.visitor_message.index("先认识灰塑"), result.visitor_message.index(self.primary.name))
        self.assertEqual(result.visitor_message.count("先认识灰塑"), 1)

    def test_repeat_craft_is_only_a_brief_recap(self):
        coverage = commit_introductions(None, [{"subject_kind": "craft", "subject_id": "灰塑", "source_ids": ["S07"], "introduced_by": "stop_guidance", "node_id": self.program.node_id, "turn_id": "turn:1"}])
        bundle = self._bundle(coverage=coverage)
        result = render_guidance_evidence(self.program, bundle)
        self.assertNotIn("先认识灰塑", result.visitor_message)
        self.assertIn("已经介绍过", result.visitor_message)
        self.assertNotIn("灰塑", result.rendered_craft_ids)
        self.assertEqual(coverage.introduced_craft_ids, ("灰塑",))

    def test_first_ornament_contains_location_shape_and_story_backed_by_sources(self):
        result = render_guidance_evidence(self.program, self._bundle())
        self.assertIn(self.primary.name, result.visitor_message)
        self.assertIn(self.primary.craft, result.visitor_message)
        self.assertIn("独角", result.visitor_message)
        self.assertIn("传说", result.visitor_message)
        self.assertIn("S08", result.used_source_ids)
        self.assertIn(self.primary.ornament_id, result.rendered_ornament_ids)

    def test_story_origin_keeps_a_distinct_object_level_context_detail(self):
        """A story title alone is not a sufficiently informative first introduction.

        The two sentences are verbatim object-level facts from the audited
        ``踏雪寻梅`` entry.  The test uses a reviewed front-courtyard item
        mapping and verifies that the renderer keeps a later story detail,
        rather than expanding it from model memory.
        """
        base = plan_stop_program("stop_front_courtyard_north", 360, detail_level="deep")
        item = replace(
            base.selected_items[0],
            ornament_id="orn_051",
            name="踏雪寻梅",
            craft="木雕",
            raw_location="首进中路",
            observation_location="首进中路",
        )
        program = replace(base, selected_items=(item,))

        def rag(query: str) -> str:
            if "定义 材料 技法 建筑位置 特点" in query:
                evidence = [_entry(
                    "07_ornament_crafts.md", "木雕", "S10",
                    "木雕是岭南传统建筑装饰工艺，可通过雕刻呈现人物和故事题材。",
                )]
            else:
                evidence = [_entry(
                    "08_ornament_items.md", "踏雪寻梅", "S11",
                    "“踏雪寻梅”源自唐代诗人孟浩然的故事。孟浩然冒着大雪骑驴到霸陵赏梅，写下诗篇《南阳阻雪》。",
                )]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        result = render_guidance_evidence(program, build_guidance_evidence_bundle(program, None, rag))
        self.assertIn("源自唐代诗人孟浩然的故事", result.visitor_message)
        self.assertIn("骑驴到霸陵赏梅", result.visitor_message)
        self.assertIn("S11", result.used_source_ids)
        self.assertNotIn("来源：S", result.visitor_message)

    def test_documented_story_scenes_are_kept_for_reviewed_objects_at_their_nodes(self):
        """Story detail is allowed only when the same object packet supplies it."""
        fixtures = (
            (
                "label_moon_platform", "orn_041", "截江夺阿斗", "木雕", "中进聚贤堂南面（檐板）",
                "故事取材于《三国演义》。孙权用计骗取孙夫人携刘备的儿子阿斗回东吴探母。画面为张飞闻讯后，手持丈八蛇矛在江中拦截东吴船只夺阿斗的情景。",
                "张飞闻讯后",
            ),
            (
                "stop_rear_west_courtyard", "orn_034", "赤壁之战", "木雕", "中进聚贤堂屏风",
                "故事取材于《三国演义》。刮东风之夜，周瑜部下黄盖假装降曹，带着装满柴草的战船驶向曹军。中部描绘了曹军士兵在“曹”字大旗下乘船逃窜的情景。",
                "黄盖假装降曹",
            ),
            (
                "stop_rear_west_courtyard", "orn_049", "三顾茅庐", "木雕", "中进西路屏风",
                "故事取材于《三国演义》。刘备三顾茅庐，问计于诸葛亮。雕饰中下方是刘备、关羽和张飞冒风雪前往寻访的情景。",
                "刘备、关羽和张飞",
            ),
        )
        for node_id, ornament_id, name, craft, raw_location, content, required_detail in fixtures:
            with self.subTest(ornament_id=ornament_id):
                base = plan_stop_program(node_id, 360, detail_level="deep")
                item = replace(
                    base.selected_items[0], ornament_id=ornament_id, name=name, craft=craft,
                    raw_location=raw_location, observation_location=raw_location,
                )
                program = replace(base, selected_items=(item,))

                def rag(query: str) -> str:
                    if "定义 材料 技法 建筑位置 特点" in query:
                        evidence = [_entry(
                            "07_ornament_crafts.md", craft, "S10",
                            f"{craft}是岭南传统建筑装饰工艺，可通过雕刻或塑造呈现人物和故事题材。",
                        )]
                    else:
                        evidence = [_entry("08_ornament_items.md", name, "S11", content)]
                    return json.dumps({"evidence": evidence}, ensure_ascii=False)

                result = render_guidance_evidence(program, build_guidance_evidence_bundle(program, None, rag))
                self.assertIn(name, result.visitor_message)
                self.assertIn(required_detail, result.visitor_message)
                self.assertIn(raw_location, result.visitor_message)
                self.assertEqual(result.rendered_ornament_ids, (ornament_id,))
                self.assertIn("S11", result.used_source_ids)
                self.assertNotIn("来源：S", result.visitor_message)

    def test_wrong_object_evidence_cannot_enter_primary_segment_or_candidate(self):
        result = render_guidance_evidence(self.program, self._bundle(wrong_primary=True))
        # 福禄寿 may still be the separately selected second reviewed object;
        # the safety boundary is that it cannot stand in for the primary item.
        self.assertNotIn(f"{self.primary.name}是一件", result.visitor_message)
        self.assertFalse(any(candidate.subject_id == self.primary.ornament_id for candidate in result.eligible_coverage_candidates))

    def test_missing_craft_evidence_removes_craft_candidate(self):
        result = render_guidance_evidence(self.program, self._bundle(no_craft=True))
        self.assertNotIn("灰塑", result.rendered_craft_ids)
        self.assertTrue(any("没有合格的工艺总述证据" in warning for warning in result.warnings))

    def test_short_budget_preserves_core_prefix_and_omits_later_items(self):
        short = replace(
            self.program,
            budget_seconds=120,
            selected_items=(replace(self.primary, planned_seconds=120), self.second),
        )
        result = render_guidance_evidence(short, self._bundle())
        self.assertEqual(result.rendered_ornament_ids, (self.primary.ornament_id,))
        self.assertEqual(result.omitted_ornament_ids, (self.second.ornament_id,))
        self.assertLessEqual(result.allocated_content_seconds, result.content_budget_seconds)
        self.assertFalse(any(candidate.subject_id == self.second.ornament_id for candidate in result.eligible_coverage_candidates))
        self.assertNotIn("两个观察重点", result.visitor_message)

    def test_three_item_stops_use_evidence_specific_observation_cues_without_fixed_count(self):
        for node_id in ("stop_front_courtyard_north", "stop_rear_west_courtyard"):
            with self.subTest(node_id=node_id):
                program = plan_stop_program(node_id, 360, detail_level="deep")
                result = render_guidance_evidence(program, self._bundle(program))
                self.assertEqual(len(result.rendered_ornament_ids), 3)
                self.assertNotIn("两个观察重点", result.visitor_message)
                self.assertNotIn("轮廓、细部与周围构件的关系", result.visitor_message)
                for item in program.selected_items:
                    self.assertIn(f"{item.name}的构图呈现", result.visitor_message)

    def test_missing_ornament_evidence_omits_generic_observation_and_coverage(self):
        result = render_guidance_evidence(self.program, self._bundle(no_ornaments=True))
        self.assertEqual(result.rendered_ornament_ids, ())
        self.assertFalse(any(candidate.subject_kind == "ornament" for candidate in result.eligible_coverage_candidates))
        self.assertNotIn("轮廓、细部与周围构件的关系", result.visitor_message)
        self.assertTrue(any("没有合格的单件文物证据" in warning for warning in result.warnings))

    def test_listen_only_has_no_task_or_question(self):
        profile = create_visitor_profile(interests=["灰塑"], detail_level="standard", interaction_mode="listen_only")
        result = render_guidance_evidence(self.program, self._bundle(), build_guidance_policy(profile))
        self.assertNotIn("无需回答", result.visitor_message)
        self.assertNotIn("？", result.visitor_message)
        self.assertNotIn("任务", result.visitor_message)
        self.assertNotIn("说说", result.visitor_message)

    def test_paths_are_hidden_sources_are_only_used_when_rendered_and_inputs_are_unchanged(self):
        bundle = self._bundle()
        before_program = self.program.to_dict()
        before_bundle = bundle.to_dict()
        result = render_guidance_evidence(self.program, bundle)
        self.assertNotIn(".md", result.visitor_message)
        self.assertNotIn("来源：S", result.visitor_message)
        self.assertEqual(self.program.to_dict(), before_program)
        self.assertEqual(bundle.to_dict(), before_bundle)
        self.assertEqual(result.used_source_ids, tuple(sorted(set(result.used_source_ids))))
        self.assertEqual(result, render_guidance_evidence(self.program, bundle))

    def test_object_sections_and_completion_prompt_are_flat_and_separate(self):
        result = render_guidance_evidence(self.program, self._bundle())
        message = result.visitor_message
        for item in self.program.selected_items:
            self.assertIn(f"【观察对象：{item.name}】\n\n{item.name}是一件", message)
        self.assertIn("【下一步】\n\n讲解结束后，您可确认是否完成本点参观。", message)
        self.assertFalse(any(line.startswith(("- ", "* ", "  - ", "  * ")) for line in message.splitlines()))


if __name__ == "__main__":
    unittest.main()
