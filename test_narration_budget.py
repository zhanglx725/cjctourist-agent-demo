"""Budget preflight and continuation contracts for long narration."""

from __future__ import annotations

from dataclasses import replace
import json
import math
import unittest

from narration_budget import (
    NarrationBudgetMode,
    advance_continuation,
    classify_continuation_action,
    continuation_from_decision,
    decide_narration_budget,
    narration_continuation_from_dict,
    plan_for_budget_decision,
    resume_plan_from_continuation,
)
from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import StyleBrief, compile_style_brief
from narration_validation import validate_stop_guidance_role_narration
from role_narration_generation import generate_role_narration, role_connector_text


def _brief() -> StyleBrief:
    components = {
        "opening": ("开场表达八个字符",),
        "closing": ("收束表达八个字符",),
        "appreciation": ("完整模式使用的一段较长欣赏表达用于制造预算差异",),
    }
    for topic in ("space", "craft", "ornament"):
        components[f"{topic}_intro"] = ("单元引入八个字符",)
        components[f"{topic}_observation"] = ("完整模式中的较长观察承接表达用于增加连接语预算",)
        components[f"{topic}_transition"] = ("单元转换八个字符",)
    return StyleBrief(
        schema_version="narration_style_v1", style_id="neutral",
        display_name="测试", persona={}, generation_policy={},
        acceptance_profile={}, prohibited_patterns=(), few_shot_examples=(),
        point_narration_components=components,
    )


def _plan(unit_count: int, budget: int) -> NarrationContentPlan:
    topics = ("space", "craft", "ornament")
    facts = tuple(
        NarrationFact(
            f"{topics[index % 3]}:unit-{index}:000",
            f"{topics[index % 3]}_detail",
            f"审核事实第{index}项保持原文。",
        )
        for index in range(unit_count)
    )
    return NarrationContentPlan(
        stop_id="front", style_id="neutral", language="zh",
        budget_seconds=budget, facts=facts, must_include=(), already_covered=(),
        must_not_claim=(), interaction_allowed=True,
        allocated_content_seconds=unit_count * 10,
    )


class NarrationBudgetTests(unittest.TestCase):
    def test_one_fact_selects_full_scaffold_when_budget_is_sufficient(self):
        decision = decide_narration_budget(_plan(1, 60), _brief())
        self.assertEqual(decision.mode, NarrationBudgetMode.FULL)
        self.assertEqual(len(decision.selected_fact_ids), 1)
        self.assertFalse(decision.deferred_fact_ids)

    def test_three_units_select_full_compact_split_and_fallback_by_budget(self):
        decisions = {
            mode: decide_narration_budget(_plan(3, budget), _brief()).mode
            for mode, budget in {
                "full": 90, "compact": 45, "split": 25, "fallback": 5,
            }.items()
        }
        self.assertEqual(decisions, {
            "full": NarrationBudgetMode.FULL,
            "compact": NarrationBudgetMode.COMPACT,
            "split": NarrationBudgetMode.SPLIT,
            "fallback": NarrationBudgetMode.FALLBACK,
        })

    def test_twelve_units_split_on_fact_unit_boundary_without_reordering(self):
        plan = _plan(12, 25)
        decision = decide_narration_budget(plan, _brief())
        self.assertEqual(decision.mode, NarrationBudgetMode.SPLIT)
        self.assertEqual(decision.selected_fact_ids, (plan.facts[0].fact_id,))
        self.assertEqual(
            decision.deferred_fact_ids,
            tuple(fact.fact_id for fact in plan.facts[1:]),
        )

    def test_split_with_craft_and_ornament_keeps_first_object_in_arrival_turn(self):
        facts = (
            NarrationFact("craft:grey:000", "craft_background", "审核工艺事实。"),
            NarrationFact("ornament:lion:000", "object_detail", "审核文物事实。"),
            NarrationFact("ornament:lion:001", "object_detail", "审核文物造型事实。"),
            NarrationFact("ornament:bat:000", "object_detail", "后续审核文物事实。"),
        )
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh",
            budget_seconds=30, facts=facts, must_include=(), already_covered=(),
            must_not_claim=(), interaction_allowed=True,
            allocated_content_seconds=31,
        )
        decision = decide_narration_budget(plan, _brief())
        self.assertEqual(decision.mode, NarrationBudgetMode.SPLIT)
        self.assertEqual(
            decision.selected_fact_ids,
            tuple(fact.fact_id for fact in facts[:3]),
        )
        self.assertEqual(decision.reason_code, "first_object_scope_fits")

    def test_child_multi_unit_preflight_matches_rendered_scaffold_budget(self):
        facts = tuple(
            [
                NarrationFact(
                    f"craft:stucco:{index:03d}", "craft_detail",
                    f"审核工艺事实第{index + 1}句保持原文。",
                )
                for index in range(4)
            ]
            + [
                NarrationFact(
                    f"ornament:{unit_id}:{index:03d}", "object_detail",
                    f"审核对象{unit_label}第{index + 1}句保持原文。",
                )
                for unit_id, unit_label in (("orn_005", "甲"), ("orn_008", "乙"))
                for index in range(4)
            ]
        )
        source_plan = NarrationContentPlan(
            stop_id="front", style_id="child", language="zh",
            budget_seconds=60, facts=facts, must_include=(),
            already_covered=(), must_not_claim=(), interaction_allowed=True,
            allocated_content_seconds=45,
        )
        brief = compile_style_brief("child")
        decision = decide_narration_budget(source_plan, brief)
        self.assertEqual(decision.mode, NarrationBudgetMode.COMPACT)
        turn_plan = plan_for_budget_decision(source_plan, decision)
        self.assertIsNotNone(turn_plan)
        assert turn_plan is not None
        response = json.dumps({
            "schema_version": "role_narration_candidate_v1",
            "style_id": "child",
            "public_text": "".join(
                f"[[FACT_{index:03d}]]" for index in range(len(facts))
            ),
            "used_fact_ids": [fact.fact_id for fact in facts],
            "omitted_fact_ids": [],
            "self_check": {
                "added_new_facts": False,
                "role_consistent": True,
                "within_budget": True,
            },
        }, ensure_ascii=False)
        candidate = generate_role_narration(turn_plan, brief, lambda _: response)
        self.assertEqual(candidate.generation_status, "generated")
        validation = validate_stop_guidance_role_narration(
            candidate, turn_plan, brief, compact=True,
        )
        self.assertEqual(
            validation.validation_status, "accepted", validation.to_dict(),
        )
        self.assertEqual(sum(
            value in candidate.public_text
            for value in brief.point_narration_components["ornament_micro_observation"]
        ), 2)
        connector_chars = len("".join(role_connector_text(
            candidate.public_text, turn_plan,
        ).split()))
        self.assertEqual(decision.connector_seconds, math.ceil(connector_chars / 4))

    def test_continuation_tracks_only_published_and_deferred_facts(self):
        plan = _plan(3, 25)
        decision = decide_narration_budget(plan, _brief())
        continuation = continuation_from_decision(
            plan, decision, freshness_token="route-v3:front",
        )
        self.assertIsNotNone(continuation)
        assert continuation is not None
        self.assertTrue(continuation.is_fresh(
            stop_id="front", style_id="neutral",
            freshness_token="route-v3:front",
        ))
        self.assertFalse(continuation.is_fresh(
            stop_id="next", style_id="neutral",
            freshness_token="route-v3:front",
        ))
        self.assertEqual(
            set(continuation.published_fact_ids) & set(continuation.remaining_fact_ids),
            set(),
        )
        self.assertEqual(
            tuple(fact.statement for fact in continuation.remaining_facts),
            tuple(fact.statement for fact in plan.facts[1:]),
        )

    def test_invalid_plan_fails_closed(self):
        plan = replace(_plan(1, 60), status="rejected")
        decision = decide_narration_budget(plan, _brief())
        self.assertEqual(decision.mode, NarrationBudgetMode.FALLBACK)
        self.assertEqual(decision.selected_fact_ids, ())

    def test_continuation_commands_are_narrow_and_deterministic(self):
        self.assertEqual(classify_continuation_action("继续。"), "continue")
        self.assertEqual(classify_continuation_action("下一部分"), "continue")
        self.assertEqual(classify_continuation_action("先讲工艺"), "craft")
        self.assertEqual(classify_continuation_action("跳过剩余内容"), "skip")
        self.assertIsNone(classify_continuation_action("继续前往下一站"))

    def test_serialized_continuation_restores_reviewed_fact_text(self):
        plan = _plan(3, 25)
        continuation = continuation_from_decision(
            plan, decide_narration_budget(plan, _brief()),
            freshness_token="route-v3:front",
        )
        assert continuation is not None
        restored = narration_continuation_from_dict(continuation.to_dict())
        self.assertEqual(restored, continuation)
        assert restored is not None
        resumed = resume_plan_from_continuation(restored, action="continue")
        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertEqual(
            tuple(fact.statement for fact in resumed.facts),
            tuple(fact.statement for fact in plan.facts[1:]),
        )

    def test_craft_resume_filters_only_existing_reviewed_craft_units(self):
        plan = _plan(3, 25)
        continuation = continuation_from_decision(
            plan, decide_narration_budget(plan, _brief()), freshness_token="fresh",
        )
        assert continuation is not None
        resumed = resume_plan_from_continuation(continuation, action="craft")
        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertTrue(all(fact.topic_kind == "craft" for fact in resumed.facts))

    def test_advance_is_idempotent_and_completes_once(self):
        plan = _plan(3, 25)
        continuation = continuation_from_decision(
            plan, decide_narration_budget(plan, _brief()), freshness_token="fresh",
        )
        assert continuation is not None
        first_id = continuation.remaining_fact_ids[0]
        advanced = advance_continuation(continuation, (first_id,))
        self.assertNotIn(first_id, advanced.remaining_fact_ids)
        self.assertEqual(advance_continuation(advanced, (first_id,)), advanced)
        completed = advance_continuation(advanced, advanced.remaining_fact_ids)
        self.assertEqual(completed.status, "completed")
        self.assertFalse(completed.remaining_fact_ids)

    def test_malformed_or_overlapping_continuation_fails_closed(self):
        plan = _plan(3, 25)
        continuation = continuation_from_decision(
            plan, decide_narration_budget(plan, _brief()), freshness_token="fresh",
        )
        assert continuation is not None
        value = continuation.to_dict()
        value["published_fact_ids"] = [value["remaining_fact_ids"][0]]
        self.assertIsNone(narration_continuation_from_dict(value))


if __name__ == "__main__":
    unittest.main()
