"""Pure safety checks for comparison-card retrieval."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import comparison_retrieval
from knowledge_card_contract import KnowledgeCard


def _gated_card(card_id: str, objects: list[str]) -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id,
        card_type="comparison",
        runtime_status="attributed_only",
        allowed_capabilities=("attributed_comparison",),
        allowed_scenarios=("study", "professional"),
        source_refs=("CMPREF_TEST",),
        applicable_node_ids=(),
        limitations=("必须归因。",),
        raw_payload={
            "comparison_id": card_id,
            "comparison_objects": objects,
            "scope_zh": "测试范围",
            "dimensions": ["材料与工艺"],
            "similarities_zh": ["测试相同点"],
            "differences_zh": ["测试差异"],
            "limitations_zh": "测试限制",
        },
    )


class ComparisonRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        comparison_retrieval.load_comparison_cards.cache_clear()
        self.cards = {
            "cmp_grey": {
                "comparison_id": "cmp_grey",
                "theme_zh": "广州灰塑与山东鄄城砖塑",
                "comparison_level": "craft_special_topic",
                "comparison_objects": ["广州灰塑", "山东鄄城砖塑"],
                "claim_strength": "research_only",
                "visitor_conclusion_zh": "研究限定结论",
                "on_site_observation_prompt": "观察材料。",
                "source_refs": ["REF_1"],
                "limitations_zh": "不得作价值排名。",
            },
            "cmp_confirmed": {
                "comparison_id": "cmp_confirmed",
                "theme_zh": "陈家祠与广州城市文化层",
                "comparison_level": "urban_cultural_position",
                "comparison_objects": ["陈氏书院", "沙面"],
                "claim_strength": "confirmed",
                "visitor_conclusion_zh": "已核验结论",
                "on_site_observation_prompt": "观察城市层次。",
                "source_refs": ["REF_2"],
                "limitations_zh": "仅限该范围。",
            },
        }

    def test_non_comparison_question_returns_no_cards(self) -> None:
        with patch.object(comparison_retrieval, "load_comparison_cards", return_value=self.cards):
            result = comparison_retrieval.comparison_context("陈家祠几点开门？")
        self.assertEqual(result["status"], "not_a_comparison_question")

    def test_general_query_does_not_surface_research_only_card(self) -> None:
        with patch.object(comparison_retrieval, "load_comparison_cards", return_value=self.cards):
            result = comparison_retrieval.comparison_context("广州灰塑和鄄城砖塑有什么不同？")
        self.assertEqual(result["status"], "no_general_safe_card")
        self.assertEqual(result["cards"], [])

    def test_research_query_surfaces_research_card_with_boundary(self) -> None:
        with patch.object(comparison_retrieval, "load_comparison_cards", return_value=self.cards):
            result = comparison_retrieval.comparison_context("从研究看广州灰塑和鄄城砖塑有什么不同？")
        self.assertEqual(result["status"], "ok_research_only")
        self.assertTrue(result["must_attribute"])
        self.assertEqual(result["cards"][0]["comparison_id"], "cmp_grey")
        self.assertIn("不得作价值排名", result["cards"][0]["limitations_zh"])

    def test_confirmed_card_is_available_to_general_question(self) -> None:
        with patch.object(comparison_retrieval, "load_comparison_cards", return_value=self.cards):
            result = comparison_retrieval.comparison_context("陈家祠和沙面有什么区别？")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["cards"][0]["comparison_id"], "cmp_confirmed")

    def test_gated_card_requires_both_explicit_objects(self) -> None:
        cards = {
            "grey_brick": _gated_card("grey_brick", ["灰塑", "砖塑"]),
            "grey_wood": _gated_card("grey_wood", ["灰塑", "木雕"]),
        }
        result = comparison_retrieval.retrieve_gated_comparison(
            "从研究角度比较灰塑和木雕有什么区别？",
            allow_research=True,
            registry_loader=lambda: cards,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["card"]["objects"], ["灰塑", "木雕"])

    def test_one_sided_card_never_becomes_research_comparison(self) -> None:
        cards = {"grey_brick": _gated_card("grey_brick", ["灰塑", "砖塑"])}
        result = comparison_retrieval.retrieve_gated_comparison(
            "从研究角度比较灰塑和木雕有什么区别？",
            allow_research=True,
            registry_loader=lambda: cards,
        )
        self.assertEqual(result, {"status": "no_matching_card", "card": None})


if __name__ == "__main__":
    unittest.main()
