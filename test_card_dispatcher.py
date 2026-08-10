"""P3-03 read-only CardDispatcher contract tests."""

from __future__ import annotations

from copy import deepcopy
import unittest

from card_dispatcher import dispatch_card_candidates
from guidance_policy import build_guidance_policy
from knowledge_card_contract import KnowledgeCard
from visitor_profile import create_visitor_profile


def _card(card_id: str, card_type: str, *, payload=None, status="enabled") -> KnowledgeCard:
    return KnowledgeCard(
        card_id=card_id, card_type=card_type, runtime_status=status,
        allowed_capabilities=("test",), allowed_scenarios=("deep",),
        source_refs=("S10",), applicable_node_ids=(), limitations=(),
        raw_payload=payload or {}, visitor_visible=True,
    )


class CardDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        from test_e5_narration_rendering import NarrationRenderingTests
        fixture = NarrationRenderingTests(methodName="test_first_craft_precedes_object_and_is_not_repeated")
        fixture.setUp()
        self.program = fixture.program
        self.policy = build_guidance_policy(create_visitor_profile(detail_level="deep", interests=["灰塑"]))

    def dispatch(self, **changes):
        values = {
            "node_id": self.program.node_id,
            "stop_program": self.program,
            "guidance_policy": self.policy,
            "journey_mode": "custom",
            "explicit_interests": ("灰塑",),
            "remaining_budget_seconds": 120,
            "registry_loader": lambda: {},
            "photo_selector": lambda **_: {"available": False},
        }
        values.update(changes)
        return dispatch_card_candidates(**values)

    def test_base_facts_are_first_and_no_card_is_forced_when_none_qualify(self):
        result = self.dispatch()
        self.assertEqual([item.candidate_type for item in result.candidates], ["base_object_facts"])
        self.assertTrue(result.candidates[0].required)
        self.assertTrue(result.read_only)
        self.assertEqual(result.state_writes, ())

    def test_classic_never_proactively_injects_research_or_comparison(self):
        registry = {"research_x": _card("research_x", "research_summary", payload={"topic": "灰塑"}, status="attributed_only")}
        result = self.dispatch(journey_mode="classic", registry_loader=lambda: registry)
        self.assertFalse({"research_summary", "comparison"} & {item.candidate_type for item in result.candidates})

    def test_research_requires_custom_policy_interest_attribution_and_node_mapping(self):
        import card_dispatcher
        original = card_dispatcher._research_ids
        card_dispatcher._research_ids = lambda _: ("research_x",)
        try:
            registry = {"research_x": _card("research_x", "research_summary", payload={"topic": "灰塑"}, status="attributed_only")}
            result = self.dispatch(registry_loader=lambda: registry)
            research = next(item for item in result.candidates if item.candidate_type == "research_summary")
            self.assertTrue(research.attribution_required)
            self.assertEqual(research.source_refs, ("S10",))
            denied = self.dispatch(explicit_interests=("木雕",), registry_loader=lambda: registry)
            self.assertNotIn("research_summary", {item.candidate_type for item in denied.candidates})
        finally:
            card_dispatcher._research_ids = original

    def test_photo_requires_explicit_intent_and_matching_safe_node(self):
        safe = lambda **_: {"available": True, "photo_spot": {"photo_spot_id": "photo_x", "node_id": self.program.node_id}}
        silent = self.dispatch(photo_selector=safe)
        self.assertNotIn("photo_spot", {item.candidate_type for item in silent.candidates})
        uncleared = self.dispatch(explicit_photo_intent=True, photo_selector=safe)
        self.assertNotIn("photo_spot", {item.candidate_type for item in uncleared.candidates})
        allowed = self.dispatch(explicit_photo_intent=True, photo_safety_cleared=True, photo_selector=safe)
        self.assertEqual(allowed.candidates[-1].candidate_type, "photo_spot")
        wrong = self.dispatch(explicit_photo_intent=True, photo_safety_cleared=True, photo_selector=lambda **_: {"available": True, "photo_spot": {"photo_spot_id": "x", "node_id": "other"}})
        self.assertNotIn("photo_spot", {item.candidate_type for item in wrong.candidates})

    def test_optional_candidates_share_one_remaining_budget(self):
        import card_dispatcher
        original_research = card_dispatcher._research_ids
        card_dispatcher._research_ids = lambda _: ("research_x",)
        try:
            registry = {"research_x": _card("research_x", "research_summary", payload={"topic": "灰塑"}, status="attributed_only")}
            result = self.dispatch(remaining_budget_seconds=40, registry_loader=lambda: registry)
            costs = sum(item.estimated_seconds for item in result.candidates)
            self.assertLessEqual(costs, 40)
        finally:
            card_dispatcher._research_ids = original_research

    def test_disabled_cards_budget_and_invalid_inputs_fail_closed(self):
        result = self.dispatch(remaining_budget_seconds=0, registry_loader=lambda: {"bad": _card("bad", "glossary_term", status="disabled")})
        self.assertEqual([item.candidate_type for item in result.candidates], ["base_object_facts"])
        with self.assertRaises(ValueError):
            self.dispatch(node_id="other")
        with self.assertRaises(ValueError):
            self.dispatch(journey_mode="guessed")

    def test_inputs_are_immutable_and_output_is_deterministic(self):
        before_program = deepcopy(self.program.to_dict())
        before_policy = deepcopy(self.policy.to_dict())
        first = self.dispatch()
        second = self.dispatch()
        self.assertEqual(first, second)
        self.assertEqual(self.program.to_dict(), before_program)
        self.assertEqual(self.policy.to_dict(), before_policy)


if __name__ == "__main__":
    unittest.main()
