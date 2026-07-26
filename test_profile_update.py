"""Offline C4 tests for atomic live VisitorProfile updates."""

from __future__ import annotations

import unittest

from guide_program_planner import plan_stop_program
from profile_update import apply_profile_update, is_profile_update_request
from route_planner import plan_template
from tour_interaction import initialize_interaction
from tour_state import start_tour


class ProfileUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tour = start_tour(plan_template("crafts_60"), interests=["灰塑"], detail_level="standard")
        self.interaction = initialize_interaction(self.tour)
        self.profile = {"available_minutes": 60, "interests": ["灰塑"], "detail_level": "standard"}

    def test_remaining_time_replans_then_atomically_updates_both_snapshots(self):
        result = apply_profile_update(self.profile, self.tour, self.interaction, "我只剩20分钟")
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "profile_replanned")
        self.assertEqual(result["visitor_profile"]["available_minutes"], 20)
        self.assertEqual(result["tour_state"]["available_minutes"], 20)
        self.assertEqual(result["tour_state"]["remaining_minutes"], 20)
        self.assertEqual(self.profile["available_minutes"], 60)
        self.assertEqual(self.tour["available_minutes"], 60)
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["tour_state"]["skipped_stop_ids"], [])

    def test_interest_updates_future_selection_without_reintroducing_progress(self):
        before = plan_stop_program("stop_front_courtyard_north", 300, interests=["灰塑"], detail_level="standard")
        result = apply_profile_update(self.profile, self.tour, self.interaction, "接下来想多看木雕")
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "profile_updated")
        self.assertEqual(result["visitor_profile"]["interests"], ["木雕"])
        self.assertEqual(result["tour_state"]["interests"], ["木雕"])
        self.assertEqual(result["tour_state"]["route_stop_ids"], self.tour["route_stop_ids"])
        after = plan_stop_program("stop_front_courtyard_north", 300, interests=result["tour_state"]["interests"], detail_level="standard")
        self.assertEqual(after.selected_items[0].craft, "木雕")
        self.assertNotEqual(before.selected_items[0].ornament_id, after.selected_items[0].ornament_id)

    def test_detail_level_changes_only_future_program_detail(self):
        result = apply_profile_update(self.profile, self.tour, self.interaction, "后面简单讲")
        self.assertTrue(result["ok"])
        self.assertEqual(result["tour_state"]["detail_level"], "short")
        short = plan_stop_program("stop_front_courtyard_north", 300, interests=["灰塑"], detail_level=result["tour_state"]["detail_level"])
        standard = plan_stop_program("stop_front_courtyard_north", 300, interests=["灰塑"], detail_level="standard")
        self.assertLess(len(short.selected_items), len(standard.selected_items))
        self.assertEqual(result["tour_state"]["visited_stop_ids"], [])
        self.assertEqual(result["interaction_state"], self.interaction)

    def test_invalid_or_conflicting_multi_field_update_has_no_partial_effect(self):
        original_tour = {**self.tour}
        original_profile = dict(self.profile)
        invalid = apply_profile_update(self.profile, self.tour, self.interaction, "我只剩10分钟，后面简单讲")
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["visitor_profile"], original_profile)
        self.assertEqual(invalid["tour_state"], original_tour)
        conflict = apply_profile_update(self.profile, self.tour, self.interaction, "我只剩20分钟又只剩30分钟")
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["visitor_profile"], original_profile)
        self.assertEqual(conflict["tour_state"], original_tour)

    def test_only_explicit_change_language_is_profile_update(self):
        self.assertTrue(is_profile_update_request("接下来想多看木雕"))
        self.assertTrue(is_profile_update_request("我想听深入一点"))
        self.assertTrue(is_profile_update_request("我只剩20分钟"))
        self.assertFalse(is_profile_update_request("这里的灰塑有什么特点？"))


if __name__ == "__main__":
    unittest.main()
