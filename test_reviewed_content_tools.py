"""CA-04 adapters preserve existing reviewed-content gates and state."""

from __future__ import annotations

from copy import deepcopy
import unittest

from reviewed_content_tools import (
    answer_reviewed_comparison,
    answer_reviewed_craft,
    answer_reviewed_object,
    answer_reviewed_point_inventory,
    answer_reviewed_research,
)


class ReviewedContentToolTests(unittest.TestCase):
    def test_craft_keeps_input_order_and_fails_closed_for_unknown_question(self):
        result = answer_reviewed_craft("砖雕、石雕和灰塑重点看哪里？")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.audit["crafts"], ["砖雕", "石雕", "灰塑"])
        self.assertNotIn("S10", result.message)
        self.assertEqual(answer_reviewed_craft("给我编一个新工艺故事").status, "not_eligible")

    def test_object_needs_resolved_identity_and_exact_evidence(self):
        item = {"ornament_id": "orn_005", "name": "独角狮", "craft": "灰塑", "node_id": "stop_front_courtyard_center", "raw_location": "山墙垂脊前沿"}
        evidence = [{"document": "08_ornament_items.md", "title_path": ["条目", "独角狮"], "source_ids": ["S11"], "ornament_id": "orn_005", "craft": "灰塑", "node_id": "stop_front_courtyard_center", "content": "独角狮为灰塑装饰。画面突出独角与狮身。"}]
        result = answer_reviewed_object(item, evidence)
        self.assertEqual(result.status, "ok")
        self.assertNotIn("S11", result.message)
        self.assertEqual(answer_reviewed_object({}, evidence).status, "not_eligible")

    def test_inventory_adapter_copies_state_and_does_not_write_it(self):
        state, interaction = {"current_stop_id": "x"}, {"pending": None}
        before = deepcopy((state, interaction))
        result = answer_reviewed_point_inventory("这里有什么？", state, interaction, formatter=lambda *_: {"mode": "inventory", "message": "已审核清单。", "inventory": {"node_id": "x", "ornaments": []}})
        self.assertEqual(result.status, "ok")
        self.assertEqual((state, interaction), before)

    def test_research_and_comparison_retain_existing_gates(self):
        research = answer_reviewed_research("研究灰塑", retriever=lambda *_args, **_kwargs: {"status": "no_eligible_match", "cards": []})
        self.assertEqual(research.status, "insufficient_evidence")
        comparison = answer_reviewed_comparison("灰塑和木雕比较", allow_research=False, retriever=lambda *_args, **_kwargs: {"status": "research_card_not_permitted", "card": None})
        self.assertEqual(comparison.status, "not_eligible")
        self.assertNotIn("card", comparison.message.casefold())


if __name__ == "__main__":
    unittest.main()
