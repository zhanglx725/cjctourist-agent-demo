from __future__ import annotations

import unittest

from narration_style_policy import compile_style_brief
from qa_role_shadow import apply_qa_role_scaffold, build_qa_content_plan, qa_role_components
from role_narration_generation import RoleNarrationCandidate


class QaRoleComponentTests(unittest.TestCase):
    def test_normal_and_follow_up_have_distinct_direct_answer_components(self):
        brief = compile_style_brief("ancient_scholar")
        normal = qa_role_components(brief, "tour_qa")
        follow_up = qa_role_components(brief, "qa_follow_up_detail")
        self.assertNotEqual(normal["direct_answer"], follow_up["direct_answer"])
        self.assertTrue(normal["opening"])
        self.assertTrue(normal["closing"])

    def test_scaffold_preserves_approved_answer_exactly_once(self):
        brief = compile_style_brief("child")
        plan = build_qa_content_plan(
            legacy_public_message="灰塑属于审核工艺信息。", scene_kind="tour_qa",
            role_mode={"status": "selected", "selected_style_id": "child"},
        )
        candidate = RoleNarrationCandidate(
            style_id="child", public_text=plan.legacy_public_message,
            used_fact_ids=("qa:approved_answer",), omitted_fact_ids=(),
            self_check={"added_new_facts": False, "role_consistent": True, "within_budget": True},
            model_called=True, latency_ms=1,
        )
        result = apply_qa_role_scaffold(candidate, plan, brief)
        self.assertEqual(result.public_text.count(plan.legacy_public_message), 1)
        self.assertNotIn("space", result.public_text.lower())

    def test_listen_only_components_do_not_ask_for_follow_up(self):
        components = qa_role_components(compile_style_brief("listen_only"), "tour_qa")
        text = "".join(components.values())
        self.assertNotIn("？", text)
        self.assertNotIn("?", text)
        self.assertNotIn("再问", text)


if __name__ == "__main__":
    unittest.main()
