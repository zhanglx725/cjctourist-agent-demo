"""Acceptance tests for canonical seven-craft explanations."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from langchain_core.messages import HumanMessage

from agent_graph import route_initial_request
from craft_knowledge import (
    BRIEF_FIELD_LABELS,
    CRAFT_TERMS,
    CraftKnowledgeError,
    brief_fields,
    load_craft_record,
    parse_craft_explanation_request,
    render_craft_explanation,
)
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question, build_qa_context_from_answer
from tour_state import start_tour


class CraftKnowledgeTests(unittest.TestCase):
    def setUp(self):
        base = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(base)
        arrived = handle_tour_event(
            base,
            interaction,
            "arrive_at_stop",
            node_id="stop_front_courtyard_center",
        )
        self.tour = arrived["tour_state"]
        self.interaction = arrived["interaction_state"]

    @staticmethod
    def _no_rag(_: str) -> str:
        raise AssertionError("generic craft explanations must not call vector RAG")

    def test_all_seven_canonical_sections_load_with_s10(self):
        for craft in CRAFT_TERMS:
            with self.subTest(craft=craft):
                record = load_craft_record(craft)
                self.assertEqual(record.craft, craft)
                self.assertTrue(record.fields)
                self.assertEqual(record.document, "07_ornament_crafts.md")
                self.assertEqual(record.source_ids, ("S10",))

    def test_parser_recognizes_required_brief_and_detailed_forms(self):
        cases = {
            "灰塑是什么": ("灰塑", "brief"),
            "什么是砖雕？": ("砖雕", "brief"),
            "介绍一下石雕": ("石雕", "brief"),
            "简单介绍木雕": ("木雕", "brief"),
            "简要讲讲陶塑": ("陶塑", "brief"),
            "说说铜铁铸": ("铜铁铸", "brief"),
            "彩绘是怎么做的": ("彩绘", "brief"),
            "灰塑有什么工艺特点": ("灰塑", "brief"),
            "详细讲讲灰塑": ("灰塑", "detailed"),
            "详细讲解陶塑": ("陶塑", "detailed"),
            "详细介绍砖雕": ("砖雕", "detailed"),
            "深入讲讲木雕": ("木雕", "detailed"),
            "展开讲讲陶塑": ("陶塑", "detailed"),
            "多讲一点石雕": ("石雕", "detailed"),
            "请完整介绍铜铁铸": ("铜铁铸", "detailed"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                request = parse_craft_explanation_request(text)
                self.assertIsNotNone(request)
                self.assertEqual((request.craft, request.detail_level), expected)

    def test_parser_does_not_steal_comparison_location_or_story_questions(self):
        for text in (
            "灰塑和砖雕有什么区别？",
            "月台上的石雕有什么特点？",
            "这里的灰塑有什么特点？",
            "梁山聚义砖雕是什么故事？",
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_craft_explanation_request(text))

    def test_brief_field_policy_is_complete_and_exact(self):
        self.assertEqual(set(BRIEF_FIELD_LABELS), set(CRAFT_TERMS))
        for craft in CRAFT_TERMS:
            with self.subTest(craft=craft):
                selected = brief_fields(load_craft_record(craft))
                self.assertEqual(
                    tuple(field.label for field in selected),
                    BRIEF_FIELD_LABELS[craft],
                )

    def test_twenty_eight_route_and_depth_scenarios_are_stable(self):
        for craft in CRAFT_TERMS:
            record = load_craft_record(craft)
            for detail_level in ("brief", "detailed"):
                query = (
                    f"{craft}是什么"
                    if detail_level == "brief"
                    else f"详细介绍{craft}"
                )
                expected = render_craft_explanation(record, detail_level)
                for active_tour in (False, True):
                    with self.subTest(
                        craft=craft,
                        detail_level=detail_level,
                        active_tour=active_tour,
                    ):
                        tour = self.tour if active_tour else None
                        interaction = self.interaction if active_tour else None
                        before_tour = deepcopy(tour)
                        before_interaction = deepcopy(interaction)
                        result = answer_tour_question(
                            query, tour, interaction, self._no_rag
                        )
                        self.assertTrue(result["message"].startswith(expected))
                        self.assertEqual(
                            [item["document"] for item in result["evidence"]],
                            ["07_ornament_crafts.md"],
                        )
                        self.assertEqual(
                            result["retrieval_strategy"],
                            "canonical_craft_section",
                        )
                        self.assertEqual(tour, before_tour)
                        self.assertEqual(interaction, before_interaction)
                        self.assertNotIn(".md", result["message"])
                        self.assertNotIn("- **", result["message"])
                        self.assertNotIn("DSML", result["message"])

    def test_brief_contains_only_policy_fields_and_detail_contains_all_fields(self):
        for craft in CRAFT_TERMS:
            record = load_craft_record(craft)
            brief = render_craft_explanation(record, "brief")
            detailed = render_craft_explanation(record, "detailed")
            selected_labels = set(BRIEF_FIELD_LABELS[craft])
            for field in record.fields:
                with self.subTest(craft=craft, field=field.label):
                    self.assertEqual(field.text in brief, field.label in selected_labels)
                    self.assertIn(field.text, detailed)

    def test_agent_router_sends_all_craft_explanations_to_tour_qa(self):
        for craft in CRAFT_TERMS:
            for query in (f"什么是{craft}", f"详细介绍{craft}"):
                with self.subTest(query=query):
                    state = {
                        "messages": [HumanMessage(content=query)],
                        "performance_metrics": [],
                    }
                    self.assertEqual(route_initial_request(state), "tour_qa")

    def test_brief_answer_creates_structured_context_without_knowledge_text(self):
        result = answer_tour_question(
            "灰塑是什么", None, None, self._no_rag
        )
        context = build_qa_context_from_answer("灰塑是什么", result, None)
        self.assertIsNotNone(context)
        self.assertEqual(context["subject_terms"], ("灰塑",))
        self.assertNotIn("草筋灰", str(context))
        self.assertNotIn("工艺性质", str(context))

    def test_missing_canonical_sections_fail_closed(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "crafts.md"
            path.write_text(
                "# 工艺\n\n## 灰塑：测试\n\n- **工艺性质与位置**：测试。\n",
                encoding="utf-8",
            )
            with self.assertRaises(CraftKnowledgeError):
                load_craft_record("灰塑", path)


if __name__ == "__main__":
    unittest.main()
