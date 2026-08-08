import unittest

from proactive_photo_guidance import build_photo_trigger_plan, maybe_trigger_photo_guidance


ELIGIBLE = {"a", "c", "e"}


def selector(*, node_id, **_kwargs):
    if node_id not in ELIGIBLE:
        return {"available": False, "reason": "none"}
    return {
        "available": True,
        "photo_spot": {"photo_spot_id": f"photo_{node_id}", "node_id": node_id, "title_zh": f"{node_id}点位"},
        "pose_templates": [{"instruction_zh": "自然侧身，目光看向建筑细节。"}],
        "limitations": ["请勿触摸文物或阻碍通行。"],
    }


def tour(minutes=45, current="a"):
    return {
        "selected_route_id": "route_1",
        "route_stop_ids": ["a", "b", "c", "d", "e"],
        "current_stop_id": current,
        "available_minutes": minutes,
    }


class ProactivePhotoGuidanceTests(unittest.TestCase):
    def test_count_is_bounded_by_time_and_route(self):
        self.assertEqual(build_photo_trigger_plan(tour(20), selector=selector)["max_count"], 1)
        self.assertEqual(build_photo_trigger_plan(tour(45), selector=selector)["max_count"], 2)
        self.assertEqual(build_photo_trigger_plan(tour(60), selector=selector)["max_count"], 3)

    def test_planned_stops_are_eligible_and_distributed(self):
        plan = build_photo_trigger_plan(tour(45), selector=selector)
        self.assertEqual(plan["planned_stop_ids"], ["a", "e"])

    def test_first_arrival_triggers_pose_once(self):
        first = maybe_trigger_photo_guidance(
            tour_state=tour(), existing_plan=None,
            last_tour_event={"event": "arrive_at_stop", "ok": True},
            visitor_profile={}, detailed=False, selector=selector,
        )
        self.assertTrue(first["triggered"])
        self.assertIn("自然侧身", first["message"])
        repeat = maybe_trigger_photo_guidance(
            tour_state=tour(), existing_plan=first["plan"],
            last_tour_event={"event": "arrive_at_stop", "ok": True},
            visitor_profile={}, detailed=False, selector=selector,
        )
        self.assertFalse(repeat["triggered"])

    def test_detail_and_listen_only_do_not_trigger(self):
        for detailed, profile in ((True, {}), (False, {"interaction_mode": "listen_only"})):
            result = maybe_trigger_photo_guidance(
                tour_state=tour(), existing_plan=None,
                last_tour_event={"event": "arrive_at_stop", "ok": True},
                visitor_profile=profile, detailed=detailed, selector=selector,
            )
            self.assertFalse(result["triggered"])

    def test_does_not_mutate_inputs(self):
        state = tour()
        profile = {"interests": ["灰塑"]}
        state_before = dict(state)
        profile_before = dict(profile)
        maybe_trigger_photo_guidance(
            tour_state=state, existing_plan=None,
            last_tour_event={"event": "arrive_at_stop", "ok": True},
            visitor_profile=profile, detailed=False, selector=selector,
        )
        self.assertEqual(state, state_before)
        self.assertEqual(profile, profile_before)

    def test_selector_failure_is_optional_and_fails_closed(self):
        def broken_selector(**_kwargs):
            raise RuntimeError("catalog unavailable")

        result = maybe_trigger_photo_guidance(
            tour_state=tour(), existing_plan=None,
            last_tour_event={"event": "arrive_at_stop", "ok": True},
            visitor_profile={}, detailed=False, selector=broken_selector,
        )
        self.assertFalse(result["triggered"])
        self.assertEqual(result["plan"]["max_count"], 0)


if __name__ == "__main__":
    unittest.main()
