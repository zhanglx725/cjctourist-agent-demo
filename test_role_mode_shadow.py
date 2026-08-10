from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import role_narration_generation_node, semantic_normalization_node
from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import approved_style_ids, compile_style_brief
from profile_dialogue import EXPLICIT_STYLE_PHRASES, STYLE_ALIASES
from narration_validation import validate_role_narration
from role_mode_shadow import resolve_role_mode
from role_narration_generation import (
    RoleNarrationCandidate,
    generate_role_narration,
)


class RoleModeShadowTests(unittest.TestCase):
    def test_explicit_requests_select_reviewed_roles(self):
        cases = {
            "我喜欢古风一点的讲解，帮我规划路线。": "ancient_scholar",
            "请用适合孩子理解的方式讲灰塑。": "child",
            "我只想安静听讲，不要频繁提问。": "listen_only",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                result = resolve_role_mode(text)
                self.assertEqual(result.status, "selected")
                self.assertEqual(result.selected_style_id, expected)
                self.assertEqual(result.source, "explicit_request")
                self.assertEqual(result.state_writes, ())
                self.assertFalse(result.applicability["state_mutation"])

    def test_all_eighteen_reviewed_styles_have_explicit_role_audit(self):
        for style_id in approved_style_ids():
            with self.subTest(style_id=style_id):
                phrases = STYLE_ALIASES.get(style_id) or EXPLICIT_STYLE_PHRASES[style_id]
                text = f"选择{phrases[0]}风格"
                result = resolve_role_mode(text)
                self.assertEqual(result.status, "selected")
                self.assertEqual(result.selected_style_id, style_id)
                self.assertEqual(result.source, "explicit_request")

    def test_profile_signal_is_read_only_and_does_not_infer_age(self):
        child = resolve_role_mode("", {"audience_mode": "child_friendly"})
        self.assertEqual(child.selected_style_id, "child")
        self.assertEqual(child.source, "visitor_profile")
        self.assertEqual(
            resolve_role_mode("", {"audience_mode": "standard"}).status,
            "not_requested",
        )
        self.assertEqual(
            resolve_role_mode("", {"explanation_style": ["child"]}).status,
            "not_requested",
        )
        neutral = resolve_role_mode("", {"explanation_style": "neutral"})
        self.assertEqual(neutral.selected_style_id, "neutral")
        self.assertEqual(neutral.source, "visitor_profile")

    def test_conflicting_and_unknown_roles_fail_closed(self):
        conflicting = resolve_role_mode("请用古风书生又适合孩子的方式讲解")
        self.assertEqual(conflicting.status, "clarification")
        self.assertEqual(conflicting.reason_codes, ("conflicting_role_request",))
        self.assertEqual(set(conflicting.candidate_style_ids), {"ancient_scholar", "child"})

        unknown = resolve_role_mode("请用抽象讲解模式讲解")
        self.assertEqual(unknown.status, "clarification")
        self.assertEqual(unknown.reason_codes, ("unsupported_role_request",))
        self.assertEqual(unknown.candidate_style_ids, ())

    def test_explicit_selection_can_be_carried_without_profile_write(self):
        prior = resolve_role_mode("古风一点的讲解").to_dict()
        inherited = resolve_role_mode("帮我继续", {}, prior)
        self.assertEqual(inherited.selected_style_id, "ancient_scholar")
        self.assertEqual(inherited.source, "inherited_shadow")
        self.assertEqual(inherited.state_writes, ())

    def test_semantic_normalization_records_role_shadow_on_route_request(self):
        state = {
            "messages": [HumanMessage(content="我喜欢古风一点的讲解，帮我规划路线。")],
            "visitor_profile": {
                "available_minutes": 60,
                "interests": [],
                "detail_level": "standard",
                "audience_mode": "standard",
                "knowledge_level": "general",
                "explanation_style": "standard",
                "interaction_mode": "normal",
            },
        }
        with patch("agent_graph._invoke_semantic_model", return_value='{"candidates":[],"ambiguity_reason":"no_candidate"}'):
            result = semantic_normalization_node(state)
        self.assertEqual(result["role_mode_shadow"]["selected_style_id"], "ancient_scholar")
        self.assertNotIn("tour_state", result)
        self.assertNotIn("visitor_profile", result)

    def test_selected_role_changes_only_shadow_plan_and_candidate(self):
        plan = NarrationContentPlan(
            stop_id="front", style_id="neutral", language="zh", budget_seconds=60,
            facts=(NarrationFact("craft:灰塑", "craft_background", "屋脊可见灰塑。"),),
            must_include=("approved_observation_detail",), already_covered=(),
            must_not_claim=("unreviewed_date",), interaction_allowed=True,
        )
        state = {
            "messages": [AIMessage(content="旧链讲解", additional_kwargs={"stop_guidance": True})],
            "narration_content_plan": plan.to_dict(),
            "role_mode_shadow": resolve_role_mode("请用适合孩子理解的方式讲灰塑").to_dict(),
        }
        generated = RoleNarrationCandidate(
            style_id="child", public_text="屋脊可见灰塑。我们可以仔细看看。",
            used_fact_ids=("craft:灰塑",), omitted_fact_ids=(),
            self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
            model_called=True, latency_ms=1,
        )
        with patch.dict(os.environ, {
            "CJC_READ_ONLY_ROLLOUT_MODE": "shadow",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES": "role_narration",
        }, clear=False), patch("agent_graph.generate_role_narration", return_value=generated):
            result = role_narration_generation_node(state)
        self.assertEqual(result["narration_content_plan"]["style_id"], "child")
        self.assertEqual(result["role_narration_candidate"]["style_id"], "child")
        self.assertNotIn("messages", result)
        self.assertNotIn("tour_state", result)
        self.assertNotIn("visitor_profile", result)

    def test_all_three_roles_produce_schema_valid_shadow_candidates(self):
        for style_id in ("ancient_scholar", "child", "listen_only"):
            with self.subTest(style_id=style_id):
                plan = NarrationContentPlan(
                    stop_id="front", style_id=style_id, language="zh", budget_seconds=60,
                    facts=(NarrationFact("craft:灰塑", "craft_background", "屋脊可见灰塑。"),),
                    must_include=("approved_observation_detail",), already_covered=(),
                    must_not_claim=("unreviewed_date",),
                    interaction_allowed=style_id != "listen_only",
                )

                def invoke(_: str, selected=style_id) -> str:
                    import json
                    return json.dumps({
                        "schema_version": "role_narration_candidate_v1",
                        "style_id": selected,
                        "public_text": "屋脊可见灰塑。请从容观察。" if selected == "ancient_scholar" else "屋脊可见灰塑。我们可以看看它。" if selected == "child" else "屋脊可见灰塑。",
                        "used_fact_ids": ["craft:灰塑"],
                        "omitted_fact_ids": [],
                        "self_check": {"added_new_facts": False, "role_consistent": True, "within_budget": True},
                        }, ensure_ascii=False)

                candidate = generate_role_narration(plan, compile_style_brief(style_id), invoke)
                validation = validate_role_narration(candidate, plan, compile_style_brief(style_id))
                self.assertEqual(candidate.generation_status, "generated")
                self.assertEqual(validation.validation_status, "accepted")
                self.assertEqual(candidate.style_id, style_id)


if __name__ == "__main__":
    unittest.main()
