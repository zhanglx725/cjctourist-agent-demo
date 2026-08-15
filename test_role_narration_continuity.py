from __future__ import annotations

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    atomic_read_plan_shadow_node,
    clarification_node,
    direct_route_node,
    narration_content_plan_node,
    narration_validation_node,
    post_visit_title_blessing_node,
    role_mode_confirmation_node,
    role_narration_generation_node,
    route_initial_request,
    semantic_normalization_node,
    stop_guidance_node,
    tour_event_node,
    tour_opening_node,
    visit_summary_node,
)
from role_mode_shadow import ROLE_MODE_SURFACES, resolve_role_mode
from narration_style_policy import compile_style_brief
from role_narration_generation import (
    RoleNarrationCandidate,
    apply_point_narration_scaffold,
)


ROLE_CASES = {
    "ancient_scholar": "我喜欢古风一点的讲解",
    "child": "请用适合孩子理解的方式讲",
    "listen_only": "我只想安静听讲，不需要互动",
}


class RoleNarrationContinuityTests(unittest.TestCase):
    @staticmethod
    def shadow_environment():
        return patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": (
                "presentation_content_plan,role_narration"
            ),
        }, clear=False)

    @staticmethod
    def _merge(state, update):
        return {**state, **update}

    def _route_state(self, role_record):
        route = direct_route_node({
            "messages": [HumanMessage(content="选择经典模式，30分钟路线")],
            "visitor_profile": {
                "available_minutes": 30,
                "interests": ["灰塑"],
                "detail_level": "standard",
                "route_constraint": None,
            },
        })
        return {**route, "role_mode_shadow": role_record}

    @staticmethod
    def _accepted_stop_candidate(plan, style_id):
        token_candidate = RoleNarrationCandidate(
            style_id=style_id,
            public_text="".join(fact.statement for fact in plan.facts),
            used_fact_ids=tuple(fact.fact_id for fact in plan.facts),
            omitted_fact_ids=(),
            self_check={
                "added_new_facts": False,
                "role_consistent": True,
                "within_budget": True,
            },
            model_called=True,
            latency_ms=1,
        )
        return apply_point_narration_scaffold(
            token_candidate, plan, compile_style_brief(style_id),
        )

    def test_role_applicability_contract_lists_all_five_surfaces(self):
        result = resolve_role_mode(ROLE_CASES["ancient_scholar"]).to_dict()
        self.assertEqual(result["applicability"]["surfaces"], list(ROLE_MODE_SURFACES))

    def test_natural_role_conflict_variants_are_normalized_before_llm(self):
        for text in (
            "语言风格改成静听和儿童友好",
            "儿童友好 + 静听",
            "同时使用儿童友好与静听",
        ):
            with self.subTest(text=text):
                result = resolve_role_mode(text).to_dict()
                self.assertEqual(result["status"], "clarification")
                self.assertEqual(
                    result["candidate_style_ids"], ["child", "listen_only"],
                )
                self.assertIn("conflicting_role_request", result["reason_codes"])

    def test_child_friendly_mode_is_a_single_reviewed_role(self):
        result = resolve_role_mode("儿童友好模式").to_dict()
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selected_style_id"], "child")

    def test_each_reviewed_role_survives_the_complete_shadow_journey(self):
        for role_id, request in ROLE_CASES.items():
            with self.subTest(role_id=role_id), self.shadow_environment():
                role_record = resolve_role_mode(request).to_dict()
                self.assertEqual(role_record["selected_style_id"], role_id)

                state = self._route_state(role_record)
                protected_at_start = {
                    key: deepcopy(state.get(key))
                    for key in ("visitor_profile", "active_route_plan")
                }

                route_shadow = atomic_read_plan_shadow_node(
                    state, {"configurable": {"thread_id": f"continuity-{role_id}"}},
                )
                state = self._merge(state, route_shadow)
                route_record = state["route_role_narration_evaluations"][-1]

                arrival_input = {
                    **state,
                    "messages": [HumanMessage(content="我到前院中部了")],
                }
                arrived = tour_event_node(arrival_input)
                state = self._merge(arrival_input, arrived)
                opened = tour_opening_node(
                    state, {"configurable": {"thread_id": f"continuity-{role_id}"}},
                )
                state = self._merge(state, opened)
                opening_record = state["route_role_narration_evaluations"][-1]

                guidance = stop_guidance_node(state)
                state = self._merge(state, guidance)
                planned = narration_content_plan_node(state)
                state = self._merge(state, planned)
                generated_plan = deepcopy(state["narration_content_plan"])

                def fake_generate(plan, _brief, _invoke_model):
                    return self._accepted_stop_candidate(plan, role_id)

                with patch("agent_graph.generate_role_narration", side_effect=fake_generate):
                    generated = role_narration_generation_node(state)
                state = self._merge(state, generated)
                validated = narration_validation_node(
                    state, {"configurable": {"thread_id": f"continuity-{role_id}"}},
                )
                state = self._merge(state, validated)
                stop_record = state["role_narration_evaluations"][-1]

                completion_input = {
                    **state,
                    "messages": [HumanMessage(content="完成本点")],
                }
                completed = tour_event_node(completion_input)
                state = self._merge(completion_input, completed)
                navigation_shadow = atomic_read_plan_shadow_node(
                    state, {"configurable": {"thread_id": f"continuity-{role_id}"}},
                )
                state = self._merge(state, navigation_shadow)
                navigation_record = state["route_role_narration_evaluations"][-1]

                finish_input = {
                    **state,
                    "messages": [HumanMessage(content="结束游览")],
                }
                finished = tour_event_node(finish_input)
                state = self._merge(finish_input, finished)
                state = self._merge(state, visit_summary_node(state))
                state = self._merge(state, post_visit_title_blessing_node(state))
                closing_shadow = atomic_read_plan_shadow_node(
                    state, {"configurable": {"thread_id": f"continuity-{role_id}"}},
                )
                closing_record = closing_shadow["route_role_narration_evaluations"][-1]

                records = (
                    route_record, opening_record, stop_record,
                    navigation_record, closing_record,
                )
                self.assertEqual(
                    [record.get("scene_kind", "stop_guidance") for record in records],
                    [
                        "route_planning", "route_opening", "stop_guidance",
                        "navigation", "tour_closing",
                    ],
                    records,
                )
                self.assertEqual(
                    [record["style_id"] if "style_id" in record else record["role_mode"]
                     for record in records],
                    [role_id] * 5,
                )
                self.assertEqual(
                    [record["validation_status"] for record in records],
                    ["accepted", "accepted", "rejected", "accepted", "accepted"],
                    records,
                )
                self.assertIn(
                    "style_scaffold_budget_exceeded", stop_record["reason_codes"],
                )
                self.assertTrue(stop_record["fallback_used"])
                self.assertTrue(stop_record["legacy_message_preserved"])
                self.assertTrue(all(record["active_takeover"] is False for record in records))
                self.assertTrue(all(record["state_writes"] == [] for record in records))
                self.assertEqual(state["role_mode_shadow"]["selected_style_id"], role_id)
                self.assertEqual(state["visitor_profile"], protected_at_start["visitor_profile"])
                self.assertEqual(state["active_route_plan"], protected_at_start["active_route_plan"])
                self.assertEqual(
                    generated_plan["style_id"],
                    guidance["active_narration_render_audit"]["style_id"],
                )

    def test_unrelated_turn_inherits_role_without_profile_write(self):
        prior = resolve_role_mode(ROLE_CASES["child"]).to_dict()
        inherited = resolve_role_mode(
            "陈家祠为什么又叫陈氏书院？", {}, prior,
        ).to_dict()
        self.assertEqual(inherited["selected_style_id"], "child")
        self.assertEqual(inherited["source"], "inherited_shadow")
        self.assertEqual(inherited["state_writes"], [])

    def test_conflicting_role_turn_fails_closed_without_overwriting_prior(self):
        prior = resolve_role_mode(ROLE_CASES["ancient_scholar"]).to_dict()
        conflict = resolve_role_mode(
            "既要古风书生，也要儿童友好", {}, prior,
        ).to_dict()
        self.assertEqual(conflict["status"], "clarification")
        self.assertIsNone(conflict["selected_style_id"])
        self.assertEqual(conflict["state_writes"], [])
        self.assertEqual(prior["selected_style_id"], "ancient_scholar")

    def test_role_conflict_clarifies_and_preserves_next_stop_for_generic_arrival(self):
        prior = resolve_role_mode(ROLE_CASES["ancient_scholar"]).to_dict()
        state = self._route_state(prior)

        arrived_input = {
            **state,
            "messages": [HumanMessage(content="我到前院中部了")],
        }
        state = self._merge(arrived_input, tour_event_node(arrived_input))
        completed_input = {
            **state,
            "messages": [HumanMessage(content="完成本点")],
        }
        state = self._merge(completed_input, tour_event_node(completed_input))
        pending_stop = state["tour_interaction_state"]["pending_stop_id"]
        self.assertEqual(pending_stop, "label_moon_platform")

        conflict_input = {
            **state,
            "messages": [HumanMessage(content="语言风格改成静听和儿童友好")],
        }
        with patch(
            "agent_graph._invoke_semantic_model",
            return_value='{"candidates":[],"ambiguity_reason":"no_candidate"}',
        ):
            semantic = semantic_normalization_node(conflict_input)
        conflict_state = self._merge(conflict_input, semantic)
        self.assertEqual(route_initial_request(conflict_state), "clarification")
        self.assertEqual(
            conflict_state["role_mode_shadow"]["selected_style_id"],
            "ancient_scholar",
        )
        self.assertEqual(
            conflict_state["pending_role_mode_clarification"]["status"],
            "clarification",
        )
        clarified = clarification_node(conflict_state)
        self.assertIn("只选择一种", clarified["messages"][0].content)
        for field in ("tour_state", "tour_interaction_state", "visitor_profile"):
            self.assertNotIn(field, clarified)
        state = self._merge(conflict_state, clarified)
        self.assertEqual(
            state["tour_interaction_state"]["pending_stop_id"], pending_stop,
        )

        selection_input = {
            **state,
            "messages": [HumanMessage(content="儿童友好模式")],
        }
        with patch(
            "agent_graph._invoke_semantic_model",
            return_value='{"candidates":[],"ambiguity_reason":"no_candidate"}',
        ):
            semantic = semantic_normalization_node(selection_input)
        selection_state = self._merge(selection_input, semantic)
        self.assertEqual(route_initial_request(selection_state), "role_mode_confirmation")
        confirmation = role_mode_confirmation_node(selection_state)
        self.assertEqual(
            confirmation["last_role_mode_confirmation"]["code"],
            "confirmed_and_navigation_resumed",
        )
        self.assertIn("月台", confirmation["messages"][0].content)
        self.assertEqual(confirmation["visitor_profile"]["explanation_style"], "child")
        self.assertFalse(confirmation["performance_metrics"][-1]["model_called"])
        self.assertFalse(confirmation["performance_metrics"][-1]["rag_called"])
        for field in ("tour_state", "tour_interaction_state"):
            self.assertNotIn(field, confirmation)
        state = self._merge(selection_state, confirmation)
        self.assertEqual(
            state["tour_interaction_state"]["pending_stop_id"], pending_stop,
        )

        generic_arrival_input = {
            **state,
            "messages": [HumanMessage(content="到达")],
        }
        semantic = semantic_normalization_node(generic_arrival_input)
        arrival_state = self._merge(generic_arrival_input, semantic)
        self.assertEqual(route_initial_request(arrival_state), "tour_event")
        arrival = tour_event_node(arrival_state)
        self.assertTrue(arrival["last_tour_event"]["ok"])
        self.assertEqual(arrival["last_tour_event"]["event"], "arrive_at_stop")
        self.assertEqual(arrival["tour_state"]["current_stop_id"], pending_stop)

    def test_single_role_confirmation_reexpresses_current_stop_without_rag(self):
        prior = resolve_role_mode(ROLE_CASES["ancient_scholar"]).to_dict()
        state = self._route_state(prior)
        arrived_input = {
            **state,
            "messages": [HumanMessage(content="我到前院中部了")],
        }
        state = self._merge(arrived_input, tour_event_node(arrived_input))
        state = self._merge(state, stop_guidance_node(state))
        original_tour = deepcopy(state["tour_state"])
        original_interaction = deepcopy(state["tour_interaction_state"])

        selection_input = {
            **state,
            "messages": [HumanMessage(content="儿童友好")],
        }
        with patch(
            "agent_graph._invoke_semantic_model",
            return_value='{"candidates":[],"ambiguity_reason":"no_candidate"}',
        ):
            semantic = semantic_normalization_node(selection_input)
        selection_state = self._merge(selection_input, semantic)
        self.assertEqual(route_initial_request(selection_state), "role_mode_confirmation")
        confirmation = role_mode_confirmation_node(selection_state)
        self.assertEqual(
            confirmation["last_role_mode_confirmation"]["code"],
            "current_guidance_reexpressed",
        )
        public_text = confirmation["messages"][0].content
        self.assertTrue(public_text.strip())
        self.assertNotIn("无法在不展示内部检索信息", public_text)
        self.assertNotIn("rag_tool", public_text)
        self.assertEqual(confirmation["visitor_profile"]["explanation_style"], "child")
        self.assertFalse(confirmation["performance_metrics"][-1]["model_called"])
        self.assertFalse(confirmation["performance_metrics"][-1]["rag_called"])
        self.assertNotIn("tour_state", confirmation)
        self.assertNotIn("tour_interaction_state", confirmation)
        self.assertEqual(selection_state["tour_state"], original_tour)
        self.assertEqual(selection_state["tour_interaction_state"], original_interaction)


if __name__ == "__main__":
    unittest.main()
