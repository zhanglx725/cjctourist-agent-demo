"""Offline D3 tests for D1-gated research-card retrieval."""

from __future__ import annotations

import unittest

from knowledge_card_contract import KnowledgeCard
from research_card_retrieval import format_research_answer, is_explicit_research_question, retrieve_research_cards


def _research(card_id: str, *, node_ids: list[str] | None = None, status: str = "attributed_only", raw_status: str = "reviewed") -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id, card_type="research_summary", runtime_status=status,
        allowed_capabilities=("attributed_research_viewpoint", "research_method_summary", "research_question_matching") if status != "disabled" else (),
        allowed_scenarios=("deep", "study", "professional"), source_refs=("research_source_008",),
        applicable_node_ids=tuple(node_ids or []), limitations=("Must retain research attribution.",),
        raw_payload={
            "card_id": card_id, "status": raw_status, "title_zh": f"灰塑研究 {card_id}", "topic_tags": ["灰塑"],
            "supported_questions": ["灰塑有什么研究价值？"], "author_position": "作者从工艺与空间关系解释灰塑。",
            "method_and_evidence": ["实地考察"], "guide_safe_takeaway": "用于观察灰塑。",
            "agreement_and_limits": {"limits": "不得外推为所有灰塑的结论。"},
            "source": {"citation": "测试作者. (2026). 灰塑研究."}, "applicable_node_ids": list(node_ids or []),
        },
    )


class ResearchCardRetrievalTests(unittest.TestCase):
    def test_explicit_research_and_comparison_boundaries(self) -> None:
        self.assertTrue(is_explicit_research_question("从学术研究角度看灰塑有什么价值？"))
        self.assertFalse(is_explicit_research_question("灰塑是什么？"))
        self.assertFalse(is_explicit_research_question("从研究角度比较灰塑和砖雕"))

    def test_node_association_boosts_and_order_is_stable(self) -> None:
        cards = {
            "research_a": _research("research_a"),
            "research_b": _research("research_b", node_ids=["label_moon_platform"]),
        }
        result = retrieve_research_cards(
            "从研究角度看灰塑", current_node_id="label_moon_platform", registry_loader=lambda: cards
        )
        self.assertEqual([item["title_zh"] for item in result["cards"]], ["灰塑研究 research_b", "灰塑研究 research_a"])
        # Stable output has the explicitly related card first; IDs are not part
        # of visitor rendering, but are safe to assert inside this retrieval test.
        self.assertTrue(result["cards"][0]["applicable_here"])

    def test_current_node_never_substitutes_for_question_match(self) -> None:
        result = retrieve_research_cards(
            "从研究角度看冷巷通风。",
            current_node_id="label_moon_platform",
            registry_loader=lambda: {"research_a": _research("research_a", node_ids=["label_moon_platform"])},
        )
        self.assertEqual(result["status"], "no_eligible_match")
        self.assertEqual(result["cards"], [])

    def test_disabled_and_background_cards_never_run(self) -> None:
        cards = {
            "disabled": _research("disabled", status="disabled"),
            "background": _research("background", raw_status="background"),
        }
        result = retrieve_research_cards("论文如何解释灰塑？", registry_loader=lambda: cards)
        self.assertEqual(result["status"], "no_eligible_match")
        self.assertEqual(result["cards"], [])

    def test_limit_is_two_and_ties_are_stable(self) -> None:
        cards = {f"research_{letter}": _research(f"research_{letter}") for letter in "cba"}
        result = retrieve_research_cards("从学术角度看灰塑", registry_loader=lambda: cards, limit=9)
        self.assertEqual(len(result["cards"]), 2)
        self.assertEqual([item["title_zh"] for item in result["cards"]], ["灰塑研究 research_a", "灰塑研究 research_b"])

    def test_registry_failure_degrades_safely(self) -> None:
        result = retrieve_research_cards("从学术角度看灰塑", registry_loader=lambda: (_ for _ in ()).throw(OSError("broken")))
        self.assertEqual(result["status"], "registry_unavailable")
        self.assertEqual(result["cards"], [])

    def test_professional_adds_method_but_keeps_attribution_and_limits(self) -> None:
        context = retrieve_research_cards(
            "从学术角度看灰塑", registry_loader=lambda: {"research_a": _research("research_a")}
        )
        general = format_research_answer(context, knowledge_level="general")
        professional = format_research_answer(context, knowledge_level="professional")
        self.assertIn("研究指出", general)
        self.assertIn("适用范围与限制", general)
        self.assertIn("研究指出", professional)
        self.assertIn("适用范围与限制", professional)
        self.assertNotIn("实地考察", general)
        self.assertIn("实地考察", professional)
        self.assertNotIn("research_a", professional)

    def test_selected_payload_never_exposes_local_file_or_card_id(self) -> None:
        context = retrieve_research_cards(
            "从学术角度看灰塑", registry_loader=lambda: {"research_a": _research("research_a")}
        )
        message = format_research_answer(context, knowledge_level="general")
        self.assertNotIn("research_a", message)
        self.assertNotIn("local_file", message)


if __name__ == "__main__":
    unittest.main()
