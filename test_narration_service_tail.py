from __future__ import annotations

import unittest
from dataclasses import replace

from narration_service_tail import (
    COMPLETION_PROMPT,
    build_stop_service_tail,
    compose_stop_presentation,
    validate_stop_service_tail,
)
from route_planner import plan_template
from tour_state import start_tour


class NarrationServiceTailTests(unittest.TestCase):
    STOP_ID = "stop_front_courtyard_center"

    def tour_state(self):
        state = start_tour(plan_template("highlights_30"))
        state["current_stop_id"] = self.STOP_ID
        return state

    def test_builds_completion_and_fresh_next_stop_in_fixed_order(self):
        tour = self.tour_state()
        tail = build_stop_service_tail(tour_state=tour)

        self.assertEqual(tail.status, "ready")
        self.assertEqual(tail.next_stop_id, "label_moon_platform")
        self.assertEqual(
            [unit.service_kind for unit in tail.units],
            ["completion_prompt", "next_stop"],
        )
        self.assertEqual(tail.units[0].public_text, COMPLETION_PROMPT)
        self.assertIn("完成本点后，下一站：月台", tail.units[1].public_text)
        self.assertNotIn("【", " ".join(unit.public_text for unit in tail.units))

        validation = validate_stop_service_tail(
            tail, tour_state=tour, photo_plan=None, publish=True,
        )
        self.assertEqual(validation.validation_status, "accepted")
        self.assertEqual(validation.reason_codes, ())

    def test_reviewed_photo_guidance_is_request_only_and_not_in_main_tail(self):
        tour = self.tour_state()
        photo_plan = {
            "schema_version": "proactive_photo_guidance_v1",
            "route_id": tour["selected_route_id"],
            "planned_stop_ids": [self.STOP_ID],
            "triggered_stop_ids": [self.STOP_ID],
        }
        tail = build_stop_service_tail(
            tour_state=tour,
            photo_guidance_message=(
                "【打卡姿势建议】前庭门厅\n"
                "在允许停留的位置自然站立，轻微侧身望向建筑。"
            ),
            photo_spot_id="photo:front",
            photo_plan=photo_plan,
        )

        self.assertEqual(
            [unit.service_kind for unit in tail.units],
            ["completion_prompt", "next_stop"],
        )
        validation = validate_stop_service_tail(
            tail, tour_state=tour, photo_plan=photo_plan, publish=True,
        )
        self.assertEqual(validation.validation_status, "accepted")
        self.assertNotIn("自然站立", validation.public_text)

    def test_stale_route_and_invalid_public_text_fail_closed(self):
        tour = self.tour_state()
        tail = build_stop_service_tail(tour_state=tour)
        stale_tour = {**tour, "selected_route_id": "different-route"}
        stale = validate_stop_service_tail(
            tail, tour_state=stale_tour, photo_plan=None, publish=True,
        )
        self.assertEqual(stale.validation_status, "rejected")
        self.assertIn("service_tail_stale", stale.reason_codes)

        bad_units = (
            tail.units[0],
            replace(tail.units[1], public_text="【下一步】伪造导航。"),
        )
        malformed = validate_stop_service_tail(
            replace(tail, units=bad_units),
            tour_state=tour,
            photo_plan=None,
            publish=True,
        )
        self.assertEqual(malformed.validation_status, "rejected")
        self.assertIn("service_public_text_invalid", malformed.reason_codes)

    def test_partial_continuation_does_not_publish_service_tail(self):
        validation = validate_stop_service_tail(
            None, tour_state=self.tour_state(), photo_plan=None, publish=False,
        )
        self.assertEqual(validation.validation_status, "accepted")
        self.assertEqual(validation.public_text, "")
        self.assertEqual(validation.service_unit_kinds, ())

    def test_composition_separates_main_narration_and_service_text(self):
        text = compose_stop_presentation(
            "先看眼前这处。 这里可见一处装饰。",
            f"{COMPLETION_PROMPT} 完成本点后，下一站：月台。",
        )
        self.assertEqual(
            text,
            "先看眼前这处。 这里可见一处装饰。\n\n"
            f"{COMPLETION_PROMPT} 完成本点后，下一站：月台。",
        )
        self.assertIn("\n\n", text)


if __name__ == "__main__":
    unittest.main()
