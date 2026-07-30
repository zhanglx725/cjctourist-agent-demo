"""Offline D2 tests for eligibility-gated terminology answers."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from knowledge_card_contract import KnowledgeCard
from route_planner import plan_template
from term_card_runtime import answer_term_question, is_explicit_term_question, rank_term_candidates
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question
from tour_state import start_tour


def _card(card_id: str, zh: str, *, enabled: bool = True, en: str = "term english") -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id,
        card_type="glossary_term",
        runtime_status="enabled" if enabled else "disabled",
        allowed_capabilities=("definition_zh", "pinyin", "en_translation", "keyword_retrieval") if enabled else (),
        allowed_scenarios=("general",),
        source_refs=("S10",),
        applicable_node_ids=(),
        limitations=(),
        raw_payload={"term_id": card_id, "zh": zh, "pinyin": "Ce Shi", "en": en, "short_definition_zh": "一项已审核术语定义。", "domain": "decorative_crafts"},
    )


class TermCardRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        tour = start_tour(plan_template("highlights_30"))
        interaction = initialize_interaction(tour)
        result = handle_tour_event(tour, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        self.tour = result["tour_state"]
        self.interaction = result["interaction_state"]

    def test_reviewed_definition_and_english_are_deterministic(self) -> None:
        definition = answer_term_question("灰塑是什么？", self.tour, self.interaction)
        english = answer_term_question("灰塑英文怎么说？", self.tour, self.interaction)
        self.assertEqual(definition["mode"], "term_card")
        self.assertEqual(definition["term"]["card_id"], "term_lime_plaster_relief")
        self.assertIn("以石灰为主料", definition["message"])
        self.assertIn("松鹤延年", definition["message"])
        self.assertNotIn("S10", definition["message"])
        self.assertEqual(definition["term"]["source_ids"], ["S10"])
        self.assertIn("lime-plaster relief", english["message"])
        self.assertNotIn("S10", english["message"])

    def test_definition_uses_at_most_two_reviewed_instances_without_claiming_visibility(self) -> None:
        result = answer_term_question("灰塑是什么？", None, None)
        self.assertIn("陈家祠", result["message"])
        self.assertIn("杏林春燕", result["message"])
        self.assertIn("松鹤延年", result["message"])
        self.assertNotIn("你眼前", result["message"])
        self.assertNotIn("S10", result["message"])
        self.assertLessEqual(len(result["term_instances"]), 2)
        self.assertEqual(
            [(item["ornament_id"], item["craft"]) for item in result["term_instances"]],
            [("orn_026", "灰塑"), ("orn_022", "灰塑")],
        )

    def test_current_node_instance_is_ranked_first_and_is_limited_by_visibility_boundary(self) -> None:
        result = answer_term_question("石雕是什么？", self.tour, self.interaction)
        self.assertEqual(result["term_instances"][0]["ornament_id"], "orn_080")
        self.assertIn("当前点与上述实例存在审核关联", result["message"])
        self.assertIn("以现场为准", result["message"])
        self.assertNotIn("一定能看到", result["message"])
        self.assertNotIn("source_ids", result["message"])

    def test_pinyin_domain_and_aliases_only_use_approved_fields(self) -> None:
        pinyin = answer_term_question("灰塑的拼音是什么？", self.tour, self.interaction)
        domain = answer_term_question("灰塑属于什么工艺领域？", self.tour, self.interaction)
        aliases = answer_term_question("灰塑有哪些审核过的英文别名？", self.tour, self.interaction)
        self.assertIn("Hui Su", pinyin["message"])
        self.assertIn("装饰工艺", domain["message"])
        self.assertIn("lime-plaster relief", aliases["message"])

    def test_draft_english_is_blocked_without_leaking_translation(self) -> None:
        result = answer_term_question("墀头英文怎么说？", self.tour, self.interaction)
        self.assertEqual(result["mode"], "term_card_unavailable")
        self.assertIn("尚未通过英文输出审核", result["message"])
        self.assertNotIn("chitous", result["message"])

    def test_current_association_is_a_hint_not_visibility_claim(self) -> None:
        result = answer_term_question("灰塑是什么？", self.tour, self.interaction)
        self.assertIn("审核关联", result["message"])
        self.assertIn("以现场为准", result["message"])
        no_tour = answer_term_question("灰塑是什么？", None, None)
        self.assertNotIn("当前点与上述实例", no_tour["message"])
        self.assertNotIn("以现场为准", no_tour["message"])

    def test_ambiguous_terms_clarify_instead_of_selecting_randomly(self) -> None:
        cards = {"term_a": _card("term_a", "同名术语"), "term_b": _card("term_b", "同名术语")}
        result = answer_term_question("同名术语是什么？", None, None, registry_loader=lambda: cards)
        self.assertEqual(result["mode"], "term_card_clarification")

    def test_current_node_association_only_boosts_candidate_sorting(self) -> None:
        cards = {"term_a": _card("term_a", "同名术语"), "term_b": _card("term_b", "同名术语")}
        ranked = rank_term_candidates("同名术语是什么？", cards, associated_ids={"term_b"})
        self.assertEqual([card.card_id for card in ranked], ["term_b", "term_a"])

    def test_missing_registry_safely_falls_back_to_existing_rag(self) -> None:
        self.assertIsNone(answer_term_question("灰塑是什么？", self.tour, self.interaction, registry_loader=lambda: {}))
        result = answer_tour_question(
            "陌生术语是什么？", self.tour, self.interaction,
            lambda query: json.dumps({"query": query, "evidence": []}, ensure_ascii=False),
        )
        self.assertEqual(result["mode"], "rag")
        self.assertIn("陌生术语", result["retrieval_query"])

    def test_comparison_is_not_a_term_question_and_states_are_immutable(self) -> None:
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        self.assertFalse(is_explicit_term_question("灰塑和砖雕有什么区别？"))
        result = answer_tour_question(
            "灰塑和砖雕有什么区别？", self.tour, self.interaction,
            lambda query: json.dumps({"query": query, "evidence": []}, ensure_ascii=False),
        )
        self.assertEqual(result["mode"], "comparison_rag_fallback")
        self.assertNotEqual(result["mode"], "term_card")
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)

    def test_term_answers_do_not_change_route_or_active_program(self) -> None:
        self.tour["active_stop_program"] = {"node_id": "stop_front_courtyard_center", "selected_items": []}
        before_tour, before_interaction = deepcopy(self.tour), deepcopy(self.interaction)
        answer_term_question("灰塑是什么？", self.tour, self.interaction)
        self.assertEqual(self.tour, before_tour)
        self.assertEqual(self.interaction, before_interaction)


if __name__ == "__main__":
    unittest.main()
