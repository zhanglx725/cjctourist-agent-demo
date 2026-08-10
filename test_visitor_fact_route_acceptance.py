"""Dual-mode acceptance tests for reviewed facts, calculations, and routes."""

from __future__ import annotations

import json
import re
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from agent_graph import (
    build_agent_graph,
    direct_rag_node,
    direct_route_node,
    llm_think_node,
    route_initial_request,
    semantic_normalization_node,
    tour_qa_node,
)
from semantic_normalization import SemanticCandidate
from single_fact_answer import (
    identify_single_fact_kind,
    single_fact_categories,
    single_fact_categories_for_kind,
    single_fact_retrieval_query,
    single_fact_retrieval_query_for_kind,
)


EVIDENCE = [
    {
        "category": "history_architecture",
        "document": "02_history_architecture.md",
        "title_path": ["历史、建筑与文化特色", "历史沿革"],
        "source_ids": ["S02", "S04"],
        "content": (
            "1888 年，陈氏书院建祠公所成立并开始筹建。"
            "馆方历史页面写“1893 年落成”；"
            "广州市文化广电旅游局页面写“1888 年筹建、1894 年建成”。"
            "1959 年以陈氏书院为馆址成立广东民间工艺馆。"
            "广东民间工艺馆于 1983 年 2 月 13 日复馆并重新对外开放。"
            "1994 年“广东民间工艺馆”更名为“广东民间工艺博物馆”。"
        ),
    },
    {
        "category": "basic_info",
        "document": "01_basic_info.md",
        "title_path": ["基础信息", "信息卡"],
        "source_ids": ["S01"],
        "content": (
            "馆址：陈家祠（陈氏书院）\n"
            "地址：广州市荔湾区中山七路恩龙里 34 号"
        ),
    },
    {
        "category": "basic_info",
        "document": "01_basic_info.md",
        "title_path": ["基础信息", "开放时间与入馆规则"],
        "source_ids": ["S01"],
        "content": (
            "常规开放时间：9:00–17:30。\n"
            "停止售票/停止入馆：17:00。\n"
            "常规闭馆日：每周二；法定节假日除外。"
        ),
    },
    {
        "category": "visit_service",
        "document": "03_visit_services.md",
        "title_path": ["游览服务与参观提示", "安全与参观规则"],
        "source_ids": ["S01", "S03", "S05"],
        "content": "周二闭馆（法定节假日除外）。17:00 停止入场。",
    },
    {
        "category": "ticketing_snapshot",
        "document": "06_ticketing_rules.md",
        "title_path": ["购票、预约与入馆规则", "散客购票"],
        "source_ids": ["S07"],
        "content": (
            "常规闭馆日为每周二，法定节假日除外。\n"
            "上午场检票时段：9:00–13:00。\n"
            "下午场检票时段：13:00–17:00。\n"
            "常规当日门票销售截止时间：17:00。\n"
            "4 月 15 日至 10 月 15 日实行延时开放：闭馆时间延至 18:00，"
            "下午场检票截止和当日售票截止延至 17:30。\n"
            "未携带身份证件者，可到综合服务处出示电子身份证或其他有效证件"
            "换取实体票。使用优惠票或免票入场者，应按要求出示相应证件供查验。"
        ),
    },
]
PAYLOAD = json.dumps({"evidence": EVIDENCE}, ensure_ascii=False)
FORBIDDEN_VISITOR_TOKENS = (
    ".md",
    "source_ids",
    "chunk_id",
    "title_path",
    "node_id",
    "http://",
    "https://",
    "history_architecture",
    "ticketing_snapshot",
)


def _state(text: str, initial: dict | None = None) -> dict:
    state = dict(initial or {})
    state["messages"] = [HumanMessage(content=text)]
    state["performance_metrics"] = []
    return state


class VisitorFactRouteAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.active = direct_route_node(
            _state("我有30分钟，喜欢木雕，标准讲解，帮我规划路线")
        )

    def _assert_visitor_safe(self, message: str) -> None:
        for token in FORBIDDEN_VISITOR_TOKENS:
            self.assertNotIn(token, message)
        self.assertIsNone(re.search(r"(?<![A-Za-z0-9])S\d+(?![A-Za-z0-9])", message))

    def _run_no_route(self, query: str) -> tuple[str, dict, dict]:
        request = _state(query)
        self.assertEqual(route_initial_request(request), "direct_rag")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = PAYLOAD
            retrieval = direct_rag_node(request)
        self.assertEqual(
            [call.args[0] for call in rag.invoke.call_args_list],
            [
                {
                    "query": single_fact_retrieval_query(query),
                    "categories": [category],
                }
                for category in single_fact_categories(query)
            ],
        )
        next_state = {
            **request,
            **retrieval,
            "messages": [*request["messages"], *retrieval["messages"]],
        }
        with patch("agent_graph.build_model") as build_model:
            answer = llm_think_node(next_state)
        build_model.assert_not_called()
        return answer["messages"][0].content, retrieval, answer

    def _run_active(self, query: str) -> tuple[str, dict]:
        request = _state(query, self.active)
        self.assertEqual(route_initial_request(request), "tour_qa")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = PAYLOAD
            update = tour_qa_node(request)
        self.assertEqual(
            [call.args[0] for call in rag.invoke.call_args_list],
            [
                {
                    "query": single_fact_retrieval_query(query),
                    "categories": [category],
                }
                for category in single_fact_categories(query)
            ],
        )
        self.assertNotIn("tour_state", update)
        self.assertNotIn("tour_interaction_state", update)
        return update["messages"][0].content, update

    def test_all_reviewed_fact_cases_are_equivalent_in_both_modes(self):
        cases = (
            ("陈家祠在哪一年建成？", "construction_completion", "1893 年落成", False),
            ("陈家祠是什么时候建成的？", "construction_completion", "1894 年建成", False),
            ("陈家祠何时落成？", "construction_completion", "1893 年落成", False),
            ("陈家祠哪一年开始筹建？", "construction_start", "1888 年开始筹建", False),
            ("陈家祠从筹建到落成大约经历了多久？", "construction_duration", "5 至 6 年", True),
            ("陈家祠在哪里？", "site_address", "恩龙里 34 号", False),
            ("陈家祠闭馆时间是什么时候？", "closing_time", "常规开放时段到 17:30", False),
            ("陈家祠周二开放吗？", "closed_day", "每周二闭馆", False),
            ("陈家祠几点停止入场？", "last_admission", "停止入场时间为 17:00", False),
            ("陈家祠下午场检票到几点？", "afternoon_entry_cutoff", "常规检票截止到 17:00", False),
            (
                "订了票忘带身份证，能不能进？",
                "identity_admission_workaround",
                "有替代处理方式",
                False,
            ),
            (
                "陈家祠由谁设计、在哪一天奠基？",
                "designer_and_foundation_date",
                "资料不足",
                False,
            ),
            (
                "广东民间工艺博物馆是什么时候在这里成立的？",
                "museum_establishment",
                "1959 年",
                False,
            ),
            (
                "广东民间工艺馆什么时候复馆？",
                "museum_reopening",
                "1983 年 2 月 13 日",
                False,
            ),
            (
                "广东民间工艺馆哪一年更名？",
                "museum_renaming",
                "1994 年",
                False,
            ),
        )
        for query, kind, expected, calculated in cases:
            with self.subTest(query=query):
                self.assertEqual(identify_single_fact_kind(query), kind)
                no_route_message, retrieval, answer = self._run_no_route(query)
                active_message, active = self._run_active(query)
                self.assertEqual(no_route_message, active_message)
                self.assertIn(expected, no_route_message)
                self._assert_visitor_safe(no_route_message)
                no_route_audit = retrieval["messages"][0].additional_kwargs[
                    "direct_single_fact_answer"
                ]
                self.assertEqual(
                    retrieval["performance_metrics"][-1]["fact_kind"], kind
                )
                self.assertEqual(
                    active["performance_metrics"][-1]["fact_kind"], kind
                )
                self.assertEqual(
                    retrieval["performance_metrics"][-1]["evidence_categories"],
                    active["performance_metrics"][-1]["evidence_categories"],
                )
                self.assertEqual(
                    bool(no_route_audit.get("calculation")), calculated
                )
                self.assertEqual(
                    active["performance_metrics"][-1]["deterministic_calculation"],
                    calculated,
                )

    def test_service_answers_keep_operational_fields_separate(self):
        closing, _, _ = self._run_no_route("陈家祠闭馆时间是什么时候？")
        self.assertIn("17:30", closing)
        self.assertIn("18:00", closing)
        self.assertIn("不是同一概念", closing)
        admission, _, _ = self._run_no_route("陈家祠几点停止入场？")
        self.assertIn("17:00", admission)
        self.assertIn("不是正式闭馆时间", admission)
        afternoon, _, _ = self._run_no_route("陈家祠下午场检票到几点？")
        self.assertIn("17:00", afternoon)
        self.assertIn("17:30", afternoon)
        self.assertIn("官方当日公告", afternoon)

    def test_identity_admission_synonyms_are_equivalent_in_both_modes(self):
        queries = (
            "忘带身份证怎么进馆？",
            "身份证丢失了还能入馆吗？",
            "证件不在身上怎么检票？",
            "没带实体身份证怎么办？",
            "身份证落在酒店了还能进去吗？",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(identify_single_fact_kind(query), "identity_admission_workaround")
                no_route_message, no_route_retrieval, _ = self._run_no_route(query)
                active_message, active_update = self._run_active(query)
                self.assertEqual(no_route_message, active_message)
                for expected in ("综合服务处", "电子身份证或其他有效证件", "换取实体票"):
                    self.assertIn(expected, no_route_message)
                self._assert_visitor_safe(no_route_message)
                audit = no_route_retrieval["messages"][0].additional_kwargs["direct_single_fact_answer"]
                self.assertIn("S07", audit["source_ids"])
                self.assertIn("S07", {source for item in active_update["retrieved_evidence"] for source in item.get("source_ids", [])})

    def test_missing_calculation_endpoint_fails_closed(self):
        start_only = json.dumps(
            {"evidence": [EVIDENCE[0] | {"content": "1888 年开始筹建。"}]},
            ensure_ascii=False,
        )
        request = _state("陈家祠从筹建到落成大约经历了多久？")
        with patch("agent_graph.chen_clan_academy_rag_search") as rag:
            rag.invoke.return_value = start_only
            retrieval = direct_rag_node(request)
        audit = retrieval["messages"][0].additional_kwargs[
            "direct_single_fact_answer"
        ]
        self.assertFalse(audit["ok"])
        self.assertIsNone(audit["calculation"])
        self.assertIn("资料不足", audit["message"])

    def test_unlisted_fact_paraphrases_share_one_controlled_path_in_both_modes(self):
        cases = (
            (
                "陈家祠最晚什么时候还能进入？",
                SemanticCandidate(
                    candidate_type="fact_last_admission",
                    evidence_span="最晚什么时候还能进入",
                    confidence=0.95,
                ),
                "last_admission",
                "17:00",
            ),
            (
                "陈家祠一般哪天歇着？",
                SemanticCandidate(
                    candidate_type="fact_closed_day",
                    evidence_span="哪天歇着",
                    confidence=0.95,
                ),
                "closed_day",
                "周二",
            ),
        )
        for query, candidate, fact_kind, expected in cases:
            with self.subTest(query=query):
                self.assertIsNone(identify_single_fact_kind(query))
                no_route = _state(query)
                with patch(
                    "agent_graph.recognize_semantic_candidate",
                    return_value=candidate,
                ):
                    no_route.update(semantic_normalization_node(no_route))
                self.assertEqual(no_route["semantic_fact_kind"], fact_kind)
                self.assertEqual(route_initial_request(no_route), "direct_rag")

                with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                    rag.invoke.return_value = PAYLOAD
                    retrieval = direct_rag_node(no_route)
                expected_calls = [
                    {
                        "query": single_fact_retrieval_query_for_kind(
                            fact_kind, fallback=query
                        ),
                        "categories": [category],
                    }
                    for category in single_fact_categories_for_kind(fact_kind)
                ]
                self.assertEqual(
                    [call.args[0] for call in rag.invoke.call_args_list],
                    expected_calls,
                )
                no_route_next = {
                    **no_route,
                    **retrieval,
                    "messages": [
                        *no_route["messages"],
                        *retrieval["messages"],
                    ],
                }
                with patch("agent_graph.build_model") as build_model:
                    no_route_answer = llm_think_node(no_route_next)
                build_model.assert_not_called()
                no_route_message = no_route_answer["messages"][0].content

                active = _state(query, self.active)
                with patch(
                    "agent_graph.recognize_semantic_candidate",
                    return_value=candidate,
                ):
                    active.update(semantic_normalization_node(active))
                self.assertEqual(route_initial_request(active), "tour_qa")
                with patch("agent_graph.chen_clan_academy_rag_search") as rag:
                    rag.invoke.return_value = PAYLOAD
                    active_update = tour_qa_node(active)
                self.assertEqual(
                    [call.args[0] for call in rag.invoke.call_args_list],
                    expected_calls,
                )
                active_message = active_update["messages"][0].content

                self.assertEqual(no_route_message, active_message)
                self.assertIn(expected, active_message)
                self._assert_visitor_safe(active_message)
                self.assertEqual(
                    retrieval["performance_metrics"][-1]["fact_kind"],
                    fact_kind,
                )
                self.assertEqual(
                    active_update["performance_metrics"][-1]["fact_kind"],
                    fact_kind,
                )

    def test_two_hour_woodcarving_deep_request_uses_route_planner(self):
        text = "选择经典模式，使用中文，给我规划两小时路线，喜欢木雕，详细讲解。"
        request = _state(text)
        self.assertEqual(route_initial_request(request), "profile_collection")
        graph = build_agent_graph(with_checkpointer=False)
        result = graph.invoke(request)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 120)
        self.assertEqual(result["visitor_profile"]["interests"], ["木雕"])
        self.assertEqual(result["visitor_profile"]["detail_level"], "deep")
        self.assertEqual(result["tour_state"]["available_minutes"], 120)
        message = result["messages"][-1].content
        self.assertIn("讲解停留顺序", message)
        self.assertIn("建议停留", message)
        self.assertIn("木雕", message)
        self.assertIn("详细讲解", message)
        self._assert_visitor_safe(message)
        nodes = [metric["node"] for metric in result["performance_metrics"]]
        self.assertIn("semantic_normalization", nodes)
        self.assertLess(nodes.index("semantic_normalization"), nodes.index("visitor_onboarding"))
        self.assertLess(nodes.index("visitor_onboarding"), nodes.index("direct_route"))

    def test_two_hour_woodcarving_request_replans_from_active_tour(self):
        text = "选择经典模式，给我规划两小时路线，喜欢木雕，详细讲解。"
        request = _state(text, self.active)
        self.assertEqual(route_initial_request(request), "profile_collection")
        result = build_agent_graph(with_checkpointer=False).invoke(request)
        self.assertEqual(result["visitor_profile"]["available_minutes"], 120)
        self.assertEqual(result["visitor_profile"]["interests"], ["木雕"])
        self.assertEqual(result["visitor_profile"]["detail_level"], "deep")
        self.assertEqual(result["tour_state"]["available_minutes"], 120)
        message = result["messages"][-1].content
        self.assertIn("讲解停留顺序", message)
        self.assertIn("木雕", message)
        self.assertIn("详细讲解", message)
        self._assert_visitor_safe(message)
        nodes = [metric["node"] for metric in result["performance_metrics"]]
        self.assertIn("semantic_normalization", nodes)
        self.assertLess(nodes.index("semantic_normalization"), nodes.index("profile_collection"))
        self.assertLess(nodes.index("profile_collection"), nodes.index("direct_route"))


if __name__ == "__main__":
    unittest.main()
