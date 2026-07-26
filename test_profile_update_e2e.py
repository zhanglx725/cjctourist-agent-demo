"""Offline C-stage end-to-end checks across route, guidance, update and QA."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from guide_program_evidence import build_stop_guidance
from guide_program_planner import plan_stop_program
from route_planner import plan_template
from tour_interaction import handle_tour_event, initialize_interaction
from tour_qa import answer_tour_question
from tour_state import start_tour
from profile_update import apply_profile_update


EVIDENCE = {
    "document": "07_ornament_crafts.md",
    "title_path": ["陈家祠建筑装饰工艺总览", "灰塑"],
    "source_ids": ["S10"],
    "content": "灰塑可用于岭南建筑的屋脊、山墙等装饰部位。",
}


def _rag(_: str) -> str:
    return json.dumps({"evidence": [EVIDENCE]}, ensure_ascii=False)


class ProfileUpdateEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {"available_minutes": 30, "interests": ["灰塑"], "detail_level": "standard"}
        initial = start_tour(plan_template("highlights_30"), interests=["灰塑"], detail_level="standard")
        interaction = initialize_interaction(initial)
        arrived = handle_tour_event(initial, interaction, "arrive_at_stop", node_id="stop_front_courtyard_center")
        self.tour = arrived["tour_state"]
        self.interaction = arrived["interaction_state"]

    def test_update_flow_keeps_audited_progress_and_changes_only_future_preferences(self):
        first = build_stop_guidance(self.tour, self.interaction, _rag)
        self.assertEqual(first["stop_program"]["node_id"], "stop_front_courtyard_center")
        self.assertEqual(first["stop_program"]["selected_items"][0]["craft"], "灰塑")
        self.assertEqual(self.tour["visited_stop_ids"], [])

        shortened = apply_profile_update(self.profile, self.tour, self.interaction, "我只剩20分钟")
        self.assertTrue(shortened["ok"])
        self.assertEqual(shortened["tour_state"]["remaining_minutes"], 20)
        self.assertEqual(shortened["tour_state"]["current_stop_id"], "stop_front_courtyard_center")
        self.assertEqual(shortened["tour_state"]["visited_stop_ids"], [])

        wood = apply_profile_update(
            shortened["visitor_profile"], shortened["tour_state"], shortened["interaction_state"],
            "接下来想多看木雕",
        )
        self.assertTrue(wood["ok"])
        future = plan_stop_program(
            "stop_front_courtyard_north", 300,
            interests=wood["tour_state"]["interests"],
            detail_level=wood["tour_state"]["detail_level"],
        )
        self.assertEqual(future.selected_items[0].craft, "木雕")

        deep = apply_profile_update(
            wood["visitor_profile"], wood["tour_state"], wood["interaction_state"], "我想听深入一点"
        )
        self.assertTrue(deep["ok"])
        deep_program = plan_stop_program(
            "stop_front_courtyard_north", 300,
            interests=deep["tour_state"]["interests"], detail_level=deep["tour_state"]["detail_level"],
        )
        self.assertEqual(deep["tour_state"]["detail_level"], "deep")
        self.assertGreater(len(deep_program.selected_items), len(future.selected_items))

    def test_skip_and_qa_do_not_flow_back_after_preference_update(self):
        skipped = handle_tour_event(
            self.tour, self.interaction, "skip_stop", node_id="label_moon_platform"
        )
        changed = apply_profile_update(
            self.profile, skipped["tour_state"], skipped["interaction_state"], "后面简单讲"
        )
        self.assertTrue(changed["ok"])
        self.assertIn("label_moon_platform", changed["tour_state"]["skipped_stop_ids"])
        self.assertNotIn("label_moon_platform", changed["tour_state"]["remaining_stop_ids"])

        before_tour = deepcopy(changed["tour_state"])
        before_interaction = deepcopy(changed["interaction_state"])
        answer_tour_question(
            "这里的灰塑有什么特点？", changed["tour_state"], changed["interaction_state"], _rag
        )
        self.assertEqual(changed["tour_state"], before_tour)
        self.assertEqual(changed["interaction_state"], before_interaction)


if __name__ == "__main__":
    unittest.main()
