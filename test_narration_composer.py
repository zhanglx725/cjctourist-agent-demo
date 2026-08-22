"""P3-04 facts-only composer and visitor-layout tests."""

from __future__ import annotations

from dataclasses import replace
import unittest

from card_dispatcher import CardDispatchPlan, CardEnhancementCandidate
from controlled_knowledge_query import is_public_visitor_message
from knowledge_card_contract import KnowledgeCard
from narration_composer import MAX_VISITOR_CHARS, compose_narration


def _card(card_id, card_type, payload, *, status="enabled", refs=("S10",), visitor_visible=True):
    return KnowledgeCard(
        card_id=card_id, card_type=card_type, runtime_status=status,
        allowed_capabilities=("test",), allowed_scenarios=("deep",),
        source_refs=refs, applicable_node_ids=(), limitations=(),
        raw_payload=payload, visitor_visible=visitor_visible,
    )


class NarrationComposerTests(unittest.TestCase):
    def setUp(self):
        from narration_rendering import render_guidance_evidence
        from test_e5_narration_rendering import NarrationRenderingTests
        fixture = NarrationRenderingTests(methodName="test_first_craft_precedes_object_and_is_not_repeated")
        fixture.setUp()
        self.program = fixture.program
        self.base = render_guidance_evidence(self.program, fixture._bundle())

    def plan(self, *candidates, budget=120):
        base = CardEnhancementCandidate(0, "base_object_facts", None, True, "reviewed")
        return CardDispatchPlan(self.program.node_id, "custom", budget, (base, *candidates), ())

    def compose(self, plan, cards, **changes):
        return compose_narration(
            stop_program=self.program, base_render=self.base, dispatch_plan=plan,
            registry_loader=lambda: cards,
            photo_selector=changes.get("photo_selector", lambda **_: {"available": False}),
        )

    def test_base_only_is_public_flat_and_display_equals_tts(self):
        result = self.compose(self.plan(), {})
        self.assertEqual(result.visitor_message, result.tts_text)
        self.assertTrue(is_public_visitor_message(result.visitor_message))
        self.assertNotRegex(result.visitor_message, r"(?m)^\s*[-*+] ")
        self.assertEqual(result.state_writes, ())

    def test_term_is_inserted_before_transition_without_internal_metadata(self):
        candidate = CardEnhancementCandidate(10, "term_explanation", "term_x", False, "reviewed", ("S10",), False, 20)
        card = _card("term_x", "glossary_term", {"zh": "灰塑", "short_definition_zh": "以石灰材料塑成的建筑装饰工艺。"})
        result = self.compose(self.plan(candidate), {"term_x": card})
        self.assertIn("术语“灰塑”", result.visitor_message)
        self.assertLess(
            result.visitor_message.index("术语“灰塑”"),
            result.visitor_message.index("如需要拍照指导"),
        )
        self.assertNotIn("【可选深入】", result.visitor_message)
        self.assertNotIn("term_x", result.visitor_message)
        self.assertNotIn("S10", result.visitor_message)
        self.assertIn("term_x", result.used_card_ids)

    def test_research_requires_reviewed_payload_attribution_limits_and_sources(self):
        candidate = CardEnhancementCandidate(20, "research_summary", "research_x", False, "match", ("RS1",), True, 40)
        payload = {
            "status": "reviewed",
            "source": {"citation": "张三, 李四. (2024). 测试研究."},
            "guide_safe_takeaway": "观察时可先看构图层次。",
            "agreement_and_limits": {"limits": "结论只适用于该研究样本。"},
        }
        card = _card("research_x", "research_summary", payload, status="attributed_only", refs=("RS1",))
        result = self.compose(self.plan(candidate), {"research_x": card})
        self.assertIn("据张三, 李四（2024）的研究", result.visitor_message)
        self.assertIn("只适用于该研究样本", result.visitor_message)
        self.assertNotIn("research_x", result.visitor_message)
        denied = self.compose(self.plan(replace(candidate, attribution_required=False)), {"research_x": card})
        self.assertNotIn("测试研究", denied.visitor_message)
        self.assertIn("research_x", denied.omitted_card_ids)

    def test_comparison_is_research_limited_and_never_becomes_base_fact(self):
        candidate = CardEnhancementCandidate(30, "comparison", "cmp_x", False, "explicit", ("CMP1",), True, 40)
        payload = {
            "claim_strength": "research_only", "visitor_conclusion_zh": "两类材料呈现不同质感。",
            "scope_zh": "仅限甲与乙。", "limitations_zh": "不能扩展为价值排序。",
        }
        card = _card("cmp_x", "comparison", payload, status="attributed_only", refs=("CMP1",))
        result = self.compose(self.plan(candidate), {"cmp_x": card})
        self.assertIn("相关比较研究认为", result.visitor_message)
        self.assertIn("不能扩展为价值排序", result.visitor_message)

    def test_photo_candidate_is_kept_out_of_main_narration(self):
        candidate = CardEnhancementCandidate(40, "photo_spot", "photo_x", False, "safe", (), False, 20)
        payload = {"title_zh": "构件细节", "recommended_capture_zh": "可拍摄局部纹样。", "boundaries_zh": "不得触摸构件。"}
        card = _card("photo_x", "photo_spot_card", payload, refs=("S11",), visitor_visible=False)
        safe = lambda **_: {"available": True, "photo_spot": {"photo_spot_id": "photo_x", "node_id": self.program.node_id}}
        result = self.compose(self.plan(candidate), {"photo_x": card}, photo_selector=safe)
        self.assertNotIn("拍摄建议", result.visitor_message)
        self.assertIn("photo_x", result.omitted_card_ids)
        wrong = self.compose(self.plan(candidate), {"photo_x": card}, photo_selector=lambda **_: {"available": False})
        self.assertNotIn("拍摄建议", wrong.visitor_message)

    def test_budget_count_length_and_bad_cards_fail_closed(self):
        candidates = tuple(CardEnhancementCandidate(10 + i, "term_explanation", f"term_{i}", False, "reviewed", ("S10",), False, 20) for i in range(3))
        cards = {f"term_{i}": _card(f"term_{i}", "glossary_term", {"zh": f"术语{i}", "short_definition_zh": "审核定义。"}) for i in range(3)}
        result = self.compose(self.plan(*candidates, budget=40), cards)
        self.assertEqual(len(result.used_card_ids), 2)
        self.assertIn("term_2", result.omitted_card_ids)
        bad = replace(candidates[0], source_refs=("FORGED",))
        denied = self.compose(self.plan(bad), cards)
        self.assertNotIn("term_0", denied.used_card_ids)
        self.assertLessEqual(len(result.visitor_message), MAX_VISITOR_CHARS)

    def test_inputs_are_immutable_and_output_is_deterministic(self):
        plan = self.plan()
        before_program = self.program.to_dict()
        before_render = self.base.to_dict()
        before_plan = plan.to_dict()
        first = self.compose(plan, {})
        second = self.compose(plan, {})
        self.assertEqual(first, second)
        self.assertEqual(self.program.to_dict(), before_program)
        self.assertEqual(self.base.to_dict(), before_render)
        self.assertEqual(plan.to_dict(), before_plan)


if __name__ == "__main__":
    unittest.main()
