"""No-network tests for A1-2 deterministic guided-tour text recognition."""

import unittest

from route_planner import plan_template
from tour_interaction import initialize_interaction
from tour_intent import classify_tour_intent, resolve_reviewed_node, validate_event_suggestion
from tour_state import finish_tour, start_tour


class TourIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tour = start_tour(plan_template("highlights_30"))
        cls.interaction = initialize_interaction(cls.tour)

    def classify(self, text: str):
        return classify_tour_intent(text, self.tour, self.interaction)

    def test_explicit_arrival_maps_known_guide_stop(self):
        decision = self.classify("我到月台了")
        self.assertEqual(decision.route_kind, "tour_event")
        self.assertEqual(decision.event_type, "arrive_at_stop")
        self.assertEqual(decision.arguments, {"node_id": "label_moon_platform"})

    def test_arrival_synonym_maps_known_node(self):
        decision = self.classify("我已经到达前院中部")
        self.assertEqual(decision.event_type, "arrive_at_stop")
        self.assertEqual(decision.arguments["node_id"], "stop_front_courtyard_center")

    def test_generic_arrival_uses_only_pending_stop_while_navigating(self):
        for wording in ("我到了", "到了"):
            with self.subTest(wording=wording):
                decision = self.classify(wording)
                self.assertEqual(decision.route_kind, "tour_event")
                self.assertEqual(decision.event_type, "arrive_at_stop")
                self.assertEqual(decision.arguments, {"node_id": "stop_front_courtyard_center"})

    def test_generic_arrival_without_active_pending_stop_still_clarifies(self):
        for wording in ("我到了", "到了"):
            with self.subTest(wording=wording):
                decision = classify_tour_intent(wording)
                self.assertEqual(decision.route_kind, "clarification")
                self.assertEqual(decision.reason_code, "arrival_node_unresolved")

    def test_self_arrival_can_resolve_non_route_spatial_node(self):
        decision = self.classify("我到首进正厅了")
        self.assertEqual(decision.event_type, "arrive_at_stop")
        self.assertEqual(decision.arguments["node_id"], "label_first_main_hall")

    def test_fact_question_with_node_is_not_arrival(self):
        decision = self.classify("月台有什么？")
        self.assertEqual(decision.route_kind, "rag_question")
        self.assertIsNone(decision.event_type)

    def test_navigation_question_is_not_arrival(self):
        decision = self.classify("月台怎么走？")
        self.assertEqual(decision.route_kind, "rag_question")
        self.assertIsNone(decision.event_type)

    def test_destination_is_not_arrival(self):
        decision = self.classify("我想去月台看看")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "destination_not_arrival")

    def test_next_stop_is_not_confirmation(self):
        decision = self.classify("下一站去哪？")
        self.assertEqual(decision.event_type, "next_stop")

    def test_next_stop_how_to_walk_is_a_navigation_event(self):
        decision = self.classify("下一站怎么走")
        self.assertEqual(decision.route_kind, "tour_event")
        self.assertEqual(decision.event_type, "next_stop")

    def test_general_named_location_how_to_walk_remains_a_question(self):
        decision = self.classify("月台怎么走")
        self.assertEqual(decision.route_kind, "rag_question")
        self.assertIsNone(decision.event_type)

    def test_completion_phrase_beats_next_stop_phrase(self):
        decision = self.classify("讲完了，去下一站")
        self.assertEqual(decision.event_type, "confirm_stop_complete")

    def test_explicit_completion_confirmation_maps_to_confirm_event(self):
        decision = self.classify("确认完成本点")
        self.assertEqual(decision.route_kind, "tour_event")
        self.assertEqual(decision.event_type, "confirm_stop_complete")

    def test_completion_question_does_not_execute_confirm_event(self):
        decision = self.classify("确认完成本点吗？")
        self.assertNotEqual(decision.event_type, "confirm_stop_complete")

    def test_explanation_end_text_maps_to_lifecycle_event(self):
        for text in ("本点讲解结束", "讲解播放结束了"):
            with self.subTest(text=text):
                decision = self.classify(text)
                self.assertEqual(decision.route_kind, "tour_event")
                self.assertEqual(decision.event_type, "explanation_finished")

    def test_contextual_skip_uses_current_route_context(self):
        decision = self.classify("这里先跳过")
        self.assertEqual(decision.event_type, "skip_stop")
        self.assertEqual(decision.arguments, {})

    def test_explicit_future_skip_keeps_reviewed_node_id(self):
        decision = self.classify("跳过月台")
        self.assertEqual(decision.event_type, "skip_stop")
        self.assertEqual(decision.arguments["node_id"], "label_moon_platform")

    def test_skip_without_route_context_requests_clarification(self):
        decision = classify_tour_intent("这里先跳过")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "skip_target_unresolved")

    def test_remaining_minutes_extracts_positive_integer(self):
        decision = self.classify("我只剩20分钟")
        self.assertEqual(decision.event_type, "replan_time")
        self.assertEqual(decision.arguments, {"available_minutes": 20})

    def test_remaining_chinese_duration_and_explicit_time_change_map_to_replan(self):
        for text, expected in (("我现在只剩三十分钟", 30), ("把时间改成一个半小时", 90)):
            with self.subTest(text=text):
                decision = self.classify(text)
                self.assertEqual(decision.event_type, "replan_time")
                self.assertEqual(decision.arguments, {"available_minutes": expected})

    def test_conflicting_remaining_durations_clarify_without_event(self):
        decision = self.classify("我只剩三十分钟或一个小时")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "ambiguous_duration")

    def test_fast_without_minutes_requests_clarification(self):
        decision = self.classify("快一点")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "missing_remaining_minutes")

    def test_detail_request_is_no_side_effect_event(self):
        decision = self.classify("再讲详细一点")
        self.assertEqual(decision.event_type, "request_stop_detail")

    def test_finish_tour_phrase(self):
        decision = self.classify("结束导览")
        self.assertEqual(decision.event_type, "finish_tour")

    def test_unknown_arrival_node_requests_clarification(self):
        decision = self.classify("我到不存在展厅了")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "arrival_node_unresolved")

    def test_duplicate_marker_name_is_ambiguous(self):
        decision = self.classify("我到中进聚贤堂了")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "ambiguous_node_name")

    def test_multiple_node_mentions_are_ambiguous(self):
        decision = self.classify("我到月台和前庭之间了")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "multiple_node_mentions")

    def test_reviewed_alias_resolves_without_llm_guess(self):
        resolution = resolve_reviewed_node("我到后进中厅了")
        self.assertEqual(resolution.node_id, "label_rear_main_hall")

    def test_multi_intent_arrival_plus_question_is_rejected(self):
        decision = self.classify("我到月台了，顺便讲讲月台石雕")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "multiple_intents")

    def test_multi_intent_arrival_plus_skip_is_rejected(self):
        decision = self.classify("我到了，然后直接跳过下一站")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "multiple_intents")

    def test_multi_intent_replan_plus_finish_is_rejected(self):
        decision = self.classify("我只剩20分钟并且结束导览")
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "multiple_intents")

    def test_new_route_request_is_distinct_from_remaining_time(self):
        decision = self.classify("我有45分钟，帮我规划路线")
        self.assertEqual(decision.route_kind, "route_request")

    def test_factual_question_is_rag_question(self):
        decision = self.classify("陈家祠是什么？")
        self.assertEqual(decision.route_kind, "rag_question")

    def test_open_conversation_remains_other(self):
        decision = self.classify("你好")
        self.assertEqual(decision.route_kind, "other")

    def test_uninitialized_next_stop_still_becomes_control_event(self):
        decision = classify_tour_intent("下一站去哪？")
        self.assertEqual(decision.route_kind, "tour_event")
        self.assertEqual(decision.event_type, "next_stop")

    def test_finished_route_is_still_classified_and_adapter_will_reject(self):
        finished = finish_tour(self.tour)
        decision = classify_tour_intent("下一站去哪？", finished, self.interaction)
        self.assertEqual(decision.event_type, "next_stop")

    def test_invalid_event_suggestion_is_rejected_before_execution(self):
        decision = validate_event_suggestion("erase_tour", {})
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "invalid_event_suggestion")

    def test_fake_node_suggestion_is_rejected_before_execution(self):
        decision = validate_event_suggestion("arrive_at_stop", {"node_id": "made_up_node"})
        self.assertEqual(decision.route_kind, "clarification")
        self.assertEqual(decision.reason_code, "invalid_node_suggestion")


if __name__ == "__main__":
    unittest.main()
