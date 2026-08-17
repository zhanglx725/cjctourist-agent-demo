from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import compile_style_brief
from narration_validation import validate_stop_guidance_role_narration
from role_discourse import (
    build_role_discourse_plan,
    compose_role_discourse,
    parse_and_validate_role_discourse,
    remember_discourse_expressions,
    role_discourse_prompt,
)
from role_narration_generation import generate_role_narration


def plan(style_id: str = "child") -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id="front", style_id=style_id, language="zh", budget_seconds=60,
        allocated_content_seconds=40, scaffold_mode="compact",
        facts=(
            NarrationFact("craft:stucco:000", "craft_background", "审核事实甲。"),
            NarrationFact("craft:stucco:001", "craft_detail", "审核事实乙。"),
            NarrationFact("ornament:lion:000", "object_detail", "审核事实丙。"),
        ),
        must_include=(), already_covered=(), must_not_claim=(),
        interaction_allowed=True,
    )


def response(style_id: str = "child") -> dict:
    return {
        "schema_version": "role_discourse_candidate_v1",
        "style_id": style_id,
        "opening": "先看看这门手艺。",
        "bridges": [
            {"slot_id": "bridge:000", "text": "制作脉络接着展开。"},
            {"slot_id": "bridge:001", "text": "再把目光转向眼前对象。"},
        ],
        "closing": "做法和样子就连起来了。",
        "self_check": {
            "added_new_facts": False,
            "role_consistent": True,
            "within_budget": True,
        },
    }


class RoleDiscourseTests(unittest.TestCase):
    def test_plan_marks_same_unit_and_topic_transition(self):
        value = build_role_discourse_plan(plan())
        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(
            [slot.relation for slot in value.bridge_slots],
            ["same_unit_continuation", "topic_transition"],
        )

    def test_safe_candidate_composes_verbatim_ordered_facts(self):
        source = plan()
        discourse = build_role_discourse_plan(source)
        assert discourse is not None
        candidate = parse_and_validate_role_discourse(
            response(), discourse, compile_style_brief("child"),
            interaction_allowed=True,
        )
        self.assertEqual(candidate.status, "generated", candidate.to_dict())
        public_text = compose_role_discourse(candidate, discourse)
        for fact in source.facts:
            self.assertEqual(public_text.count(fact.statement), 1)
        self.assertLess(
            public_text.index(source.facts[0].statement),
            public_text.index(source.facts[1].statement),
        )
        self.assertLess(
            public_text.index(source.facts[1].statement),
            public_text.index(source.facts[2].statement),
        )

    def test_prompt_assigns_relations_without_asking_model_to_reprint_facts(self):
        discourse = build_role_discourse_plan(plan())
        assert discourse is not None
        prompt = role_discourse_prompt(discourse, compile_style_brief("child"))
        self.assertIn("same_unit_continuation", prompt)
        self.assertIn("topic_transition", prompt)
        self.assertIn("完整而自然的角色讲解", prompt)
        self.assertIn("轻微童话感", prompt)
        self.assertIn("同一个短句在整组连接语中只能出现一次", prompt)

    def test_schema_order_budget_fact_and_interaction_fail_closed(self):
        for name, mutate, expected in (
            ("order", lambda value: value["bridges"].reverse(), "discourse_bridge_order_changed"),
            ("fact", lambda value: value.update(opening="传说这里有故事。"), "unapproved_discourse_fact_trigger"),
            ("internal", lambda value: value.update(closing="查看 source_id。"), "discourse_internal_leak"),
            ("interaction", lambda value: value.update(opening="请你找一找好吗？"), "discourse_interaction_violation"),
        ):
            with self.subTest(name=name):
                source = plan("dominant_ceo" if name == "interaction" else "child")
                discourse = build_role_discourse_plan(source)
                assert discourse is not None
                raw = response(source.style_id)
                mutate(raw)
                candidate = parse_and_validate_role_discourse(
                    json.dumps(raw, ensure_ascii=False), discourse,
                    compile_style_brief(source.style_id),
                    interaction_allowed=name != "interaction",
                )
                self.assertEqual(candidate.status, "rejected")
                self.assertIn(expected, candidate.reason_codes)

    def test_every_approved_style_and_full_plan_can_use_discourse(self):
        style_ids = (
            "neutral", "child", "family", "student_research", "professional",
            "listen_only", "mixed_group", "dominant_ceo", "cute_junior",
            "ancient_scholar", "warm_sister", "bestie_chat", "buddy_guide",
            "exploration_game", "photo_guide", "hostel_scholar",
            "xiguan_young_master", "cantonese_storyteller",
        )
        for style_id in style_ids:
            with self.subTest(style_id=style_id):
                self.assertIsNotNone(build_role_discourse_plan(plan(style_id)))
                self.assertEqual(compile_style_brief(style_id).style_id, style_id)
        full = plan()
        object.__setattr__(full, "scaffold_mode", "full")
        self.assertIsNotNone(build_role_discourse_plan(full))

    def test_composed_discourse_uses_semantic_paragraphs(self):
        source = plan()
        discourse = build_role_discourse_plan(source)
        assert discourse is not None
        candidate = parse_and_validate_role_discourse(
            response(), discourse, compile_style_brief("child"),
            interaction_allowed=True,
        )
        text = compose_role_discourse(candidate, discourse)
        self.assertIn("\n\n", text)
        self.assertNotIn("【", text)

    def test_enabled_generation_publishes_natural_discourse_candidate(self):
        source = plan()
        brief = compile_style_brief("child")
        with patch.dict(os.environ, {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "true",
        }, clear=False):
            candidate = generate_role_narration(
                source, brief,
                lambda _: json.dumps(response(), ensure_ascii=False),
            )
        self.assertEqual(candidate.reason_code, "natural_discourse_generated")
        self.assertIn("制作脉络接着展开。", candidate.public_text)
        self.assertEqual(
            validate_stop_guidance_role_narration(
                candidate, source, brief, compact=True,
            ).validation_status,
            "accepted",
        )

    def test_invalid_natural_discourse_uses_auditable_component_fallback(self):
        source = plan()
        brief = compile_style_brief("child")
        unsafe = response()
        unsafe["opening"] = "传说这里有故事。"
        with patch.dict(os.environ, {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "true",
        }, clear=False):
            candidate = generate_role_narration(
                source, brief,
                lambda _: json.dumps(unsafe, ensure_ascii=False),
            )
        self.assertTrue(candidate.reason_code.startswith("natural_discourse_fallback:"))
        self.assertNotIn("传说", candidate.public_text)
        self.assertTrue(any(
            value in candidate.public_text
            for value in brief.point_narration_components["compact_opening"]
        ))
        self.assertEqual(
            validate_stop_guidance_role_narration(
                candidate, source, brief, compact=True,
            ).validation_status,
            "accepted",
        )

    def test_repeated_sentence_uses_distinct_component_fallback(self):
        source = plan()
        brief = compile_style_brief("child")
        repeated = response()
        repeated["bridges"][0]["text"] = "制作脉络接着展开。制作脉络接着展开。"
        discourse = build_role_discourse_plan(source)
        assert discourse is not None
        parsed = parse_and_validate_role_discourse(
            repeated, discourse, brief, interaction_allowed=True,
        )
        self.assertEqual(parsed.status, "rejected")
        self.assertIn("repeated_discourse_sentence", parsed.reason_codes)
        with patch.dict(os.environ, {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "true",
        }, clear=False):
            candidate = generate_role_narration(
                source, brief,
                lambda _: json.dumps(repeated, ensure_ascii=False),
            )
        self.assertTrue(candidate.reason_code.startswith(
            "natural_discourse_fallback:repeated_discourse_sentence"
        ))
        result = validate_stop_guidance_role_narration(
            candidate, source, brief, compact=True,
        )
        self.assertEqual(result.validation_status, "accepted", result.to_dict())
        self.assertNotIn("repeated_role_expression", result.reason_codes)

    def test_recent_expression_is_rejected_and_memory_is_bounded(self):
        source = plan()
        opening = response()["opening"]
        discourse = build_role_discourse_plan(
            source, recent_expressions=(opening,),
        )
        assert discourse is not None
        candidate = parse_and_validate_role_discourse(
            response(), discourse, compile_style_brief("child"),
            interaction_allowed=True,
        )
        self.assertEqual(candidate.status, "rejected")
        self.assertIn("recent_discourse_expression_reused", candidate.reason_codes)
        remembered = remember_discourse_expressions(
            "新开场。新桥接。新收束。",
            tuple(f"旧表达{index}。" for index in range(12)),
        )
        self.assertEqual(len(remembered), 12)
        self.assertEqual(remembered[-3:], ("新开场。", "新桥接。", "新收束。"))

    def test_model_exception_uses_component_fallback(self):
        source = plan()
        brief = compile_style_brief("child")
        with patch.dict(os.environ, {
            "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED": "true",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED": "true",
        }, clear=False):
            candidate = generate_role_narration(
                source, brief,
                lambda _: (_ for _ in ()).throw(TimeoutError()),
            )
        self.assertEqual(candidate.generation_status, "generated")
        self.assertIn(
            "natural_discourse_fallback:model_unavailable:TimeoutError",
            candidate.reason_code,
        )


if __name__ == "__main__":
    unittest.main()
