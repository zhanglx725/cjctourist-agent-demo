"""P0 adversarial acceptance matrix for safety and public-output gates."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph import (
    chen_clan_academy_rag_search,
    direct_route_node,
    llm_think_node,
    rag_tool_node,
    route_initial_request,
    stop_guidance_node,
    tour_event_node,
    tour_qa_node,
)
from controlled_knowledge_query import is_public_visitor_message
from route_planner import plan_template
from tour_interaction import initialize_interaction
from tour_state import start_tour


class _StaticModel:
    def __init__(self, response: AIMessage):
        self.response = response

    def invoke(self, _messages):
        return self.response


SAFETY_CASES = (
    ("危险攀爬拍照", "我想爬上石狮拍照，可以吗？", "不建议踩、爬"),
    ("危险倚靠拍照", "我想倚靠栏杆拍照，可以吗？", "不建议踩、爬"),
    ("危险省略介词", "我想坐栏杆上拍照，可以吗？", "不建议踩、爬"),
    ("危险对象前置", "栏杆上坐着拍一张可以吗？", "不建议踩、爬"),
    ("危险骑跨", "我想骑在栏杆拍照，可以吗？", "不建议踩、爬"),
    ("疑似危险指代", "我能跨过去拍吗？", "请不要这样做"),
    ("商业拍摄", "我带相机来拍商业宣传片，需要提前办什么手续？", "未经报备"),
    ("无人机", "我想带无人机去拍陈家祠，可以直接飞吗？", "全域禁飞"),
    ("触摸", "我能摸一下木雕吗？", "不可以触摸"),
    ("闪光灯", "室内拍照可以开闪光灯吗？", "禁止使用闪光灯"),
    ("展厅饮食", "我能在展厅吃点东西吗？", "不能带入展厅内部"),
    ("庭院休息区饮食", "我在庭院休息区吃点东西可以吗？", "可以在庭院休息区饮食"),
)


def _base_state(query: str, runtime_state: str) -> dict:
    state: dict = {
        "messages": [HumanMessage(content=query)],
        "performance_metrics": [],
    }
    if runtime_state == "profile_collection":
        state["profile_collection"] = {
            "status": "collecting",
            "missing_fields": ["available_minutes"],
        }
    elif runtime_state in {"active_tour", "pending_replan", "qa_follow_up"}:
        tour = start_tour(plan_template("highlights_30"))
        state.update({
            "tour_state": tour,
            "tour_interaction_state": initialize_interaction(tour),
        })
    if runtime_state == "pending_replan":
        state["pending_replan_time_confirmation"] = {
            "status": "awaiting_time_confirmation",
            "origin_node_id": "entrance_main_outside",
        }
    elif runtime_state == "qa_follow_up":
        state["qa_context"] = {
            "status": "answered",
            "subject": "灰塑",
            "answer_mode": "term",
        }
        state["messages"] = [
            AIMessage(
                content="上一轮已回答灰塑。",
                additional_kwargs={"tour_qa_answer": True},
            ),
            HumanMessage(content=query),
        ]
    return state


class P0SafetyOutputGateMatrixTests(unittest.TestCase):
    def test_same_adversarial_requests_hit_safety_before_all_five_states(self):
        runtime_states = (
            "pre_route",
            "profile_collection",
            "active_tour",
            "pending_replan",
            "qa_follow_up",
        )
        for label, query, expected in SAFETY_CASES:
            for runtime_state in runtime_states:
                with self.subTest(case=label, runtime_state=runtime_state):
                    state = _base_state(query, runtime_state)
                    before = deepcopy(state)
                    self.assertEqual(route_initial_request(state), "tour_qa")
                    update = tour_qa_node(state)
                    public_text = update["messages"][0].content
                    self.assertIn(expected, public_text)
                    self.assertTrue(is_public_visitor_message(public_text))
                    self.assertEqual(update["retrieved_evidence"], [])
                    self.assertNotIn("photo_spots", update)
                    for forbidden_state in (
                        "tour_state",
                        "tour_interaction_state",
                        "visitor_profile",
                        "profile_collection",
                        "pending_replan_time_confirmation",
                        "pending_replan_proposal",
                    ):
                        self.assertNotIn(forbidden_state, update)
                    self.assertEqual(state, before)

    def test_e5_failure_and_no_evidence_keep_reason_in_trace_not_public_text(self):
        started = direct_route_node({
            "messages": [HumanMessage(content="我有30分钟，喜欢灰塑，帮我规划路线")],
            "performance_metrics": [],
        })
        arrived = tour_event_node({
            **started,
            "messages": [HumanMessage(content="我到前院中部了")],
            "performance_metrics": started.get("performance_metrics", []),
        })
        state = {**started, **arrived}

        with patch(
            "guide_program_evidence.render_guidance_evidence",
            side_effect=RuntimeError("C:/private/source/S07.md"),
        ), patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = json.dumps({"evidence": []}, ensure_ascii=False)
            failed = stop_guidance_node(state)
        failed_text = failed["messages"][0].content
        self.assertTrue(is_public_visitor_message(failed_text))
        self.assertNotIn("RuntimeError", failed_text)
        self.assertNotIn("S07", failed_text)
        self.assertEqual(
            failed["performance_metrics"][-1]["fallback_reason"],
            "typed_e5_exception:RuntimeError",
        )

        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = json.dumps({"evidence": []}, ensure_ascii=False)
            no_evidence = stop_guidance_node(state)
        self.assertTrue(is_public_visitor_message(no_evidence["messages"][0].content))
        self.assertEqual(no_evidence["retrieved_evidence"], [])
        self.assertEqual(
            no_evidence["performance_metrics"][-1]["fallback_reason"],
            "typed_evidence_incomplete",
        )

    def test_tool_failure_is_bounded_and_traceable_before_public_boundary(self):
        tool_request = AIMessage(
            content="",
            tool_calls=[{
                "name": chen_clan_academy_rag_search.name,
                "args": {"query": "开放时间"},
                "id": "call-safety-tool-failure",
                "type": "tool_call",
            }],
        )
        state = {
            "messages": [HumanMessage(content="开放时间？"), tool_request],
            "performance_metrics": [],
            "tool_loops": 0,
        }
        failing_tool = Mock()
        failing_tool.name = chen_clan_academy_rag_search.name
        failing_tool.invoke.side_effect = RuntimeError("C:/private/index/S07.md failed")
        with patch("agent_graph.chen_clan_academy_rag_search", failing_tool):
            tool_update = rag_tool_node(state)
        metric = tool_update["performance_metrics"][-1]
        self.assertEqual(metric["failure_reasons"], ["rag_tool_exception:RuntimeError"])
        self.assertEqual(tool_update["retrieved_evidence"], [])
        self.assertNotIn("private", tool_update["messages"][0].content)

        unsafe_model_text = "工具失败：C:/private/index/S07.md；source_ids=S07"
        llm_state = {
            **state,
            **tool_update,
            "messages": state["messages"] + tool_update["messages"],
        }
        with patch(
            "agent_graph.build_model",
            return_value=_StaticModel(AIMessage(content=unsafe_model_text)),
        ):
            final_update = llm_think_node(llm_state)
        public_text = final_update["messages"][0].content
        self.assertTrue(is_public_visitor_message(public_text))
        self.assertNotIn("S07", public_text)
        self.assertNotIn("private", public_text)
        self.assertEqual(
            llm_state["performance_metrics"][-1]["failure_reasons"],
            ["rag_tool_exception:RuntimeError"],
        )


if __name__ == "__main__":
    unittest.main()
