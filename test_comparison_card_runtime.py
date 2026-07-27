"""Offline D4 tests for D1-gated comparison-card selection."""

from __future__ import annotations

import unittest

from comparison_retrieval import format_gated_comparison_answer, is_explicit_comparison_question, retrieve_gated_comparison
from knowledge_card_contract import KnowledgeCard


def _comparison(card_id: str, objects: list[str], *, status: str = "attributed_only", scope: str = "仅限测试对象的研究比较。") -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id, card_type="comparison", runtime_status=status,
        allowed_capabilities=("attributed_comparison", "comparative_observation") if status != "disabled" else (),
        allowed_scenarios=("study", "professional", "explicit_research_comparison"),
        source_refs=("CMPREF_TEST",), applicable_node_ids=(), limitations=("研究专用",),
        raw_payload={
            "comparison_id": card_id, "comparison_objects": objects, "theme_zh": "测试比较主题",
            "comparison_level": "craft_special_topic", "dimensions": ["material_and_technique"],
            "similarities_zh": ["两者都可作为建筑装饰观察对象。"],
            "differences_zh": ["两者材料与制作方式不同。"], "claim_strength": "research_only",
            "scope_zh": scope, "limitations_zh": "不得外推到其他对象。",
            "on_site_observation_prompt": "请留意材料与构图。",
        },
    )


class ComparisonCardRuntimeTests(unittest.TestCase):
    def test_comparison_detection_precedes_definition_and_handles_pronouns(self) -> None:
        self.assertTrue(is_explicit_comparison_question("灰塑和砖雕有什么区别？"))
        self.assertTrue(is_explicit_comparison_question("它们有什么相同点？"))
        self.assertFalse(is_explicit_comparison_question("灰塑是什么？"))

    def test_research_card_needs_permission_and_returns_one_card(self) -> None:
        cards = {"cmp_a": _comparison("cmp_a", ["甲", "乙"])}
        denied = retrieve_gated_comparison("甲和乙有什么区别？", allow_research=False, registry_loader=lambda: cards)
        allowed = retrieve_gated_comparison("从研究角度比较甲和乙", allow_research=True, registry_loader=lambda: cards)
        self.assertEqual(denied["status"], "research_card_not_permitted")
        self.assertEqual(allowed["status"], "ok")
        self.assertIn("相同点", format_gated_comparison_answer(allowed))
        self.assertIn("适用范围与限制", format_gated_comparison_answer(allowed))
        self.assertNotIn("cmp_a", format_gated_comparison_answer(allowed))

    def test_two_objects_outrank_one_and_ties_are_stable(self) -> None:
        cards = {
            "cmp_b": _comparison("cmp_b", ["甲", "乙"], scope="仅限第二组测试对象的研究比较。"),
            "cmp_a": _comparison("cmp_a", ["甲", "乙"], scope="仅限第一组测试对象的研究比较。"),
            "cmp_single": _comparison("cmp_single", ["甲", "丙"]),
        }
        result = retrieve_gated_comparison("甲和乙有什么不同？", allow_research=True, registry_loader=lambda: cards)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["card"]["scope_zh"], "仅限第一组测试对象的研究比较。")
        # cmp_a wins the equal score by stable internal ID, without exposing it.
        self.assertEqual(result["card"]["objects"], ["甲", "乙"])

    def test_disabled_and_ambiguous_cards_fail_safely(self) -> None:
        disabled = retrieve_gated_comparison("甲和乙有什么区别？", allow_research=True, registry_loader=lambda: {"bad": _comparison("bad", ["甲", "乙"], status="disabled")})
        pronoun = retrieve_gated_comparison("它们有什么区别？", allow_research=True, registry_loader=lambda: {})
        self.assertEqual(disabled["status"], "no_matching_card")
        self.assertEqual(pronoun["status"], "ambiguous_objects")

    def test_registry_error_degrades_safely(self) -> None:
        result = retrieve_gated_comparison("甲和乙有什么区别？", allow_research=True, registry_loader=lambda: (_ for _ in ()).throw(OSError("broken")))
        self.assertEqual(result["status"], "registry_unavailable")


if __name__ == "__main__":
    unittest.main()
