"""Offline tests for the shared visitor-facing response boundary."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import (
    extended_profile_control_node,
    llm_think_node,
    stop_guidance_node,
    tour_qa_node,
)
from controlled_knowledge_query import is_public_visitor_message


class _StaticModel:
    def __init__(self, response: AIMessage):
        self.response = response

    def invoke(self, _messages):
        return self.response


class VisitorResponseBoundaryTests(unittest.TestCase):
    def test_internal_lifecycle_terms_are_not_public_text(self):
        for message in (
            "这是项目编辑拍摄候选。",
            "该对象已经审核。",
            "当前信息未核验。",
        ):
            self.assertFalse(is_public_visitor_message(message), message)

    def test_generic_llm_exit_fails_closed_without_erasing_audit_state(self):
        evidence = [{
            "document": "06_ticketing_rules.md",
            "source_ids": ["S07"],
            "chunk_id": "06:0001",
            "content": "团队订单应在购买后 30 日内申请电子发票。",
        }]
        state = {
            "messages": [HumanMessage(content="团队票怎么开发票？")],
            "retrieved_evidence": deepcopy(evidence),
            "performance_metrics": [],
            "tool_loops": 0,
        }
        unsafe = AIMessage(
            content="购买后 30 日内申请。来源：S07（06_ticketing_rules.md）",
            additional_kwargs={"audit_marker": "kept"},
        )
        with patch("agent_graph.build_model", return_value=_StaticModel(unsafe)):
            update = llm_think_node(state)

        message = update["messages"][0]
        self.assertTrue(is_public_visitor_message(message.content))
        self.assertNotIn("S07", message.content)
        self.assertNotIn(".md", message.content)
        self.assertEqual(message.additional_kwargs["audit_marker"], "kept")
        self.assertEqual(
            message.additional_kwargs["visitor_output_boundary"],
            "rejected_internal_metadata",
        )
        self.assertEqual(state["retrieved_evidence"], evidence)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("visitor_profile", update)

    def test_generic_llm_exit_keeps_safe_normal_text(self):
        safe = AIMessage(content="建议预留 30/60 分钟；这件作品采用 S 形构图。")
        state = {
            "messages": [HumanMessage(content="参观多久合适？")],
            "performance_metrics": [],
            "tool_loops": 0,
        }
        with patch("agent_graph.build_model", return_value=_StaticModel(safe)):
            update = llm_think_node(state)
        self.assertEqual(update["messages"][0].content, safe.content)
        self.assertNotIn(
            "visitor_output_boundary",
            update["messages"][0].additional_kwargs,
        )

    def test_tour_qa_exit_separates_public_text_from_structured_evidence(self):
        evidence = [{
            "document": "09_ornament_locations.md",
            "source_ids": ["S11"],
            "chunk_id": "09:0001",
            "content": "木雕与陶塑位置资料。",
        }]
        unsafe_result = {
            "message": (
                "根据本地知识库检索到的资料：09_ornament_locations.md；"
                "来源：S11；https://example.com；资料整理日期：2025-01-01。"
            ),
            "mode": "rag",
            "evidence": deepcopy(evidence),
            "point_context": None,
            "presentation": {"message": "unsafe", "phase": "explaining"},
            "pending_ornament_clarification": None,
            "single_fact": None,
            "knowledge_plan": None,
        }
        tour_state = {"phase": "navigating", "current_stop_id": None}
        visitor_profile = {"interests": ["木雕"]}
        state = {
            "messages": [HumanMessage(content="木雕和陶塑分别去哪看？")],
            "tour_state": deepcopy(tour_state),
            "visitor_profile": deepcopy(visitor_profile),
            "performance_metrics": [],
        }
        with patch("agent_graph.answer_tour_question", return_value=unsafe_result):
            update = tour_qa_node(state)

        message = update["messages"][0].content
        self.assertTrue(is_public_visitor_message(message))
        self.assertNotIn("S11", message)
        self.assertNotIn(".md", message)
        self.assertEqual(update["retrieved_evidence"], evidence)
        self.assertEqual(update["tour_presentation"]["message"], message)
        self.assertNotIn("tour_state", update)
        self.assertNotIn("visitor_profile", update)
        self.assertEqual(state["tour_state"], tour_state)
        self.assertEqual(state["visitor_profile"], visitor_profile)

    def test_stop_guidance_exit_keeps_fallback_evidence_and_coverage_safe(self):
        evidence = [{
            "document": "07_ornament_crafts.md",
            "source_ids": ["S07"],
            "chunk_id": "07:0001",
            "content": "灰塑工艺总述。",
        }]
        unsafe_result = {
            "message": "灰塑讲解。来源：S07（07_ornament_crafts.md）。",
            "status": "guided_b3_fallback",
            "evidence": deepcopy(evidence),
            "presentation": {"message": "unsafe", "phase": "explaining"},
            "stop_program": None,
            "coverage_candidates": [],
        }
        tour_state = {"phase": "arrived", "current_stop_id": "label_moon_platform"}
        state = {
            "messages": [HumanMessage(content="讲讲这里。")],
            "tour_state": deepcopy(tour_state),
            "visitor_profile": {"interests": ["灰塑"]},
            "performance_metrics": [],
        }
        with patch("agent_graph.build_stop_guidance", return_value=unsafe_result):
            update = stop_guidance_node(state)

        message = update["messages"][0].content
        self.assertTrue(is_public_visitor_message(message))
        self.assertNotIn("S07", message)
        self.assertNotIn(".md", message)
        self.assertEqual(update["retrieved_evidence"], evidence)
        self.assertEqual(update["tour_presentation"]["message"], message)
        self.assertEqual(update["narration_coverage"]["introduced_craft_ids"], [])
        self.assertNotIn("tour_state", update)
        self.assertNotIn("visitor_profile", update)
        self.assertEqual(state["tour_state"], tour_state)

    def test_current_guidance_reexpression_uses_the_same_public_boundary(self):
        evidence = [{
            "document": "08_ornament_items.md",
            "source_ids": ["S11"],
            "chunk_id": "08:0001",
            "content": "对象详情。",
        }]
        profile = {"detail_level": "detailed"}
        control = SimpleNamespace(
            kind="update",
            patch={"detail_level": "detailed"},
            reexpress_current=True,
        )
        control_result = {
            "ok": True,
            "message": "已更新讲解深度。",
            "profile": profile,
            "control": control,
        }
        rewritten = {
            "ok": True,
            "message": "对象详情。来源：S11（08_ornament_items.md）。",
            "stop_program": {"selected_items": []},
            "evidence_by_item": {},
            "evidence": deepcopy(evidence),
            "presentation": {"message": "unsafe", "phase": "explaining"},
        }
        state = {
            "messages": [HumanMessage(content="后面讲详细一点。")],
            "tour_state": {"phase": "arrived"},
            "visitor_profile": {"detail_level": "standard"},
            "performance_metrics": [],
        }
        with patch("agent_graph.apply_extended_profile_control", return_value=control_result), patch(
            "agent_graph.reexpress_current_stop_guidance", return_value=rewritten
        ):
            update = extended_profile_control_node(state)

        message = update["messages"][0].content
        self.assertTrue(is_public_visitor_message(message))
        self.assertNotIn("S11", message)
        self.assertNotIn(".md", message)
        self.assertEqual(update["retrieved_evidence"], evidence)
        self.assertEqual(update["tour_presentation"]["message"], message)


if __name__ == "__main__":
    unittest.main()
