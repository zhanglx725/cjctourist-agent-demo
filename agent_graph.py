"""Guangzhou Chen Clan Academy Agent backed by local Chinese hybrid RAG."""

from __future__ import annotations

import os
import json
import time
import re
from pathlib import Path
from typing import Annotated, Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from dotenv import load_dotenv
from rag_retrieval import ChenClanHybridRetriever
from route_planner import CATALOG_FILE, recommend_route, _read_catalog
MAX_TOOL_LOOPS = 3
DEFAULT_DEEPSEEK_MAX_TOKENS = 450
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


# Load local development settings before any model is constructed.  Existing
# process environment variables retain priority, so deployment configuration is
# never overwritten by a local .env file.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


class AgentState(TypedDict, total=False):
    """Global state. `messages` is appended and retained per thread_id."""

    messages: Annotated[list[BaseMessage], add_messages]
    tool_loops: int
    retrieved_evidence: list[dict[str, Any]]
    performance_metrics: list[dict[str, Any]]
    selected_route_id: str
    active_route_plan: dict[str, Any]


_retriever: ChenClanHybridRetriever | None = None


def get_retriever() -> ChenClanHybridRetriever:
    """Load the persisted index lazily so imports do not load embedding models."""
    global _retriever
    if _retriever is None:
        _retriever = ChenClanHybridRetriever()
        _retriever.load()
    return _retriever


def warm_rag_models() -> None:
    """Preload local RAG models for an Agent Server startup lifespan."""
    started = time.perf_counter()
    get_retriever().warm_up()
    print(f"RAG startup warm-up completed in {time.perf_counter() - started:.2f}s.")


def _append_metric(
    state: AgentState, node: str, elapsed_seconds: float, **details: Any
) -> list[dict[str, Any]]:
    """Keep a small per-request timing trail visible in LangGraph Studio state."""
    metric = {
        "node": node,
        "elapsed_seconds": round(elapsed_seconds, 4),
        **details,
    }
    return [*state.get("performance_metrics", []), metric]


def should_direct_rag(user_text: str) -> bool:
    """Skip the tool-selection LLM for clearly in-domain factual questions.

    These terms are already within the retrieval corpus and the system prompt
    requires RAG before answering them.  Conversational, preference and
    out-of-domain requests still enter the normal Agent reasoning path.
    """
    knowledge_terms = (
        "陈家祠",
        "陈氏书院",
        "灰塑",
        "木雕",
        "砖雕",
        "石雕",
        "陶塑",
        "百鸟朝凤",
        "梁山聚义",
        "月台",
    )
    return any(term in user_text for term in knowledge_terms)


def should_direct_route(user_text: str) -> bool:
    """Route requests are deterministic and need no LLM tool-selection turn."""
    route_terms = ("路线", "规划", "怎么逛", "游览", "参观顺序", "半小时", "一小时", "90分钟")
    return any(term in user_text for term in route_terms)


def _route_request_from_text(user_text: str) -> tuple[int, list[str]]:
    if re.search(r"90\s*分钟|一小时半|1\.5\s*小时", user_text):
        minutes = 90
    elif re.search(r"60\s*分钟|一小时", user_text):
        minutes = 60
    else:
        minutes = 30
    interests = [
        term
        for term in ("灰塑", "木雕", "石雕", "陶塑", "三国", "故事", "吉祥", "工艺")
        if term in user_text
    ]
    return minutes, interests


def _latest_user_text(state: AgentState) -> str:
    """Return the current visitor message when routing a fresh graph turn."""
    if not state.get("messages"):
        return ""
    content = state["messages"][-1].content
    return content if isinstance(content, str) else str(content)


@tool
def chen_clan_academy_rag_search(query: str, categories: list[str] | None = None) -> str:
    """检索本地陈家祠知识快照并返回可引用证据。

    涉及陈家祠历史、建筑、工艺、装饰、服务、票务或公告的事实问题必须调用。
    可选 categories 仅可使用：history_architecture、ornament_craft、ornament_item、
    ornament_location、basic_info、visit_service、event_notice、ticketing_snapshot。
    不确定类别时省略 categories，让系统全库检索。返回的 evidence 才是可陈述事实的边界。
    """
    try:
        evidence = get_retriever().search(query, limit=3, categories=categories)
        return json.dumps(
            {
                "query": query,
                "knowledge_base": "local_snapshot_v1",
                "evidence": [item.to_dict() for item in evidence],
                "limitations": (
                    "这是本地知识快照。票务、开放、临展、停车和无障碍等可能变化；"
                    "若证据为快照、过期或资料不足，须提示以馆方最新官方信息为准。"
                ),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {
                "query": query,
                "evidence": [],
                "error": f"本地知识检索不可用：{exc}",
            },
            ensure_ascii=False,
        )


def build_model(with_tools: bool = True):
    """Create the DeepSeek base model, binding the RAG tool when requested."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")
    max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", str(DEFAULT_DEEPSEEK_MAX_TOKENS)))
    model_name = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    model = ChatDeepSeek(model=model_name, temperature=0, max_tokens=max_tokens)
    return model.bind_tools([chen_clan_academy_rag_search]) if with_tools else model


def llm_think_node(state: AgentState) -> dict[str, Any]:
    """ReAct reasoning node: answer directly or request a knowledge-base tool call."""
    reached_limit = state.get("tool_loops", 0) >= MAX_TOOL_LOOPS
    # Only a ToolMessage immediately preceding this node belongs to the current
    # turn.  ``retrieved_evidence`` may be retained in a multi-turn checkpoint,
    # so it must not suppress retrieval for the visitor's next question.
    has_evidence = bool(state.get("messages")) and (
        isinstance(state["messages"][-1], ToolMessage)
        or bool(state["messages"][-1].additional_kwargs.get("direct_rag_evidence"))
    )
    has_route_plan = bool(state.get("messages")) and bool(
        state["messages"][-1].additional_kwargs.get("direct_route_plan")
    )
    instruction = (
        "你是陈家祠导游助手。使用用户的语言回答。涉及陈家祠的历史、建筑、装饰、"
        "工艺、服务、票务、开放或公告等事实，必须先调用 chen_clan_academy_rag_search。"
        "最终回答只能基于工具返回的 evidence；不得把模型常识补成景区事实。"
        "每项关键事实后简要标注文档名和 source_ids。若没有证据、证据有冲突，或状态为"
        "snapshot/已过期/待确认，清楚说明限制；对于实时信息，提示以馆方最新官方信息为准。"
        "可直接回答问候和与陈家祠无关的常识问题。"
        "默认采用金牌导游的简洁讲解：先直接回答，再给不超过 3 个必要要点；"
        "除非游客明确要求详细介绍、路线或清单，否则控制在约 150 至 300 个中文字符内，"
        "不要重复同一事实，不要主动扩写无关的历史、适合人群或后续服务。"
    )
    if reached_limit:
        instruction += " Tool limit reached: answer now from the existing context; do not call tools."
    if has_evidence:
        instruction += (
            " 本轮检索证据已在上下文中：现在必须基于这些 evidence 输出最终回答，"
            "不得再次调用任何工具。"
        )
        if state["messages"][-1].additional_kwargs.get("direct_rag_evidence"):
            instruction += "\n本轮本地检索证据如下：\n" + json.dumps(
                state.get("retrieved_evidence", []), ensure_ascii=False
            )
    if has_route_plan:
        instruction += (
            " 本轮已经由确定性路线规划器生成审核路线。必须以该路线的 stop_ids、"
            "full_path_node_ids、edge_ids 和时间字段为准说明；不得自行增加景点、边或步行时间。"
            " 清楚提示时间为地图估算，并可用简洁的金牌导游口吻介绍每一站的 guide_focus。\n"
            + json.dumps(state.get("active_route_plan", {}), ensure_ascii=False)
        )
    started = time.perf_counter()
    response = build_model(with_tools=not reached_limit and not has_evidence and not has_route_plan).invoke(
        [{"role": "system", "content": instruction}, *state["messages"]]
    )
    return {
        "messages": [response],
        "performance_metrics": _append_metric(
            state,
            "llm_think",
            time.perf_counter() - started,
            phase="answer" if has_evidence else "tool_decision",
            tool_loops=state.get("tool_loops", 0),
        ),
    }


def direct_route_node(state: AgentState) -> dict[str, Any]:
    """Plan and render a reviewed route without risking LLM route fabrication."""
    query = _latest_user_text(state)
    minutes, interests = _route_request_from_text(query)
    started = time.perf_counter()
    plan = recommend_route(available_minutes=minutes, interests=interests)
    plan_data = plan.to_dict()
    catalog = _read_catalog(CATALOG_FILE)
    stop_lines = []
    for index, node_id in enumerate(plan.stop_ids[1:], start=1):
        card = catalog[node_id]
        stop_lines.append(
            f"{index}. {card['stop_name']}：{card['guide_focus']}"
        )
    total_minutes = (plan.estimated_total_seconds or 0) / 60
    message = (
        f"为您推荐“{plan.display_name}”。预计总时长约 {total_minutes:.0f} 分钟"
        f"（目标 {plan.target_minutes} 分钟）。\n\n"
        "讲解停留顺序：\n"
        + "\n".join(stop_lines)
        + "\n\n"
        f"路线会经过 {len(plan.full_path_node_ids)} 个已审核空间节点、"
        f"使用 {len(plan.edge_ids)} 条已审核双向边。"
        f"时间包含讲解 {plan.estimated_explanation_seconds // 60} 分钟、"
        f"观察 {plan.estimated_observation_seconds // 60} 分钟、"
        f"互动 {plan.estimated_interaction_seconds // 60} 分钟和步行约 "
        f"{plan.estimated_walk_seconds} 秒。\n\n"
        "提示：步行时间基于官网地图与已审核路线估算，现场通行、驻足和开放情况请以馆方安排为准。"
    )
    marker = AIMessage(content=message, additional_kwargs={"direct_route_plan": True})
    return {
        "messages": [marker],
        "selected_route_id": plan.route_id,
        "active_route_plan": plan_data,
        "performance_metrics": _append_metric(
            state,
            "direct_route",
            time.perf_counter() - started,
            route_id=plan.route_id,
            requested_minutes=minutes,
            interests=interests,
        ),
    }


def direct_rag_node(state: AgentState) -> dict[str, Any]:
    """Retrieve clearly in-domain facts without an unnecessary tool-selection LLM."""
    query = _latest_user_text(state)
    started = time.perf_counter()
    content = str(chen_clan_academy_rag_search.invoke({"query": query}))
    try:
        evidence = json.loads(content).get("evidence", [])
    except json.JSONDecodeError:
        evidence = []
    marker = AIMessage(
        content="本地检索已完成，正在根据证据整理回答。",
        additional_kwargs={"direct_rag_evidence": True},
    )
    return {
        "messages": [marker],
        "retrieved_evidence": evidence,
        "performance_metrics": _append_metric(
            state,
            "direct_rag",
            time.perf_counter() - started,
            evidence_count=len(evidence),
            retrieval_methods=sorted(
                {
                    method
                    for item in evidence
                    for method in item.get("retrieval_methods", [])
                }
            ),
        ),
    }


def rag_tool_node(state: AgentState) -> dict[str, Any]:
    """Execute the tool calls requested by the latest model response."""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage):
        return {}
    results: list[ToolMessage] = []
    evidence: list[dict[str, Any]] = []
    started = time.perf_counter()
    for call in last.tool_calls:
        if call["name"] == chen_clan_academy_rag_search.name:
            content = str(chen_clan_academy_rag_search.invoke(call["args"]))
            try:
                evidence.extend(json.loads(content).get("evidence", []))
            except json.JSONDecodeError:
                pass
        else:
            content = "Unsupported tool call."
        results.append(ToolMessage(content=content, tool_call_id=call["id"]))
    return {
        "messages": results,
        "tool_loops": state.get("tool_loops", 0) + 1,
        "retrieved_evidence": evidence,
        "performance_metrics": _append_metric(
            state,
            "rag_tool",
            time.perf_counter() - started,
            evidence_count=len(evidence),
            retrieval_methods=sorted(
                {
                    method
                    for item in evidence
                    for method in item.get("retrieval_methods", [])
                }
            ),
        ),
    }


def route_after_llm(state: AgentState) -> str:
    """Route to RAG only when the model requests it and the loop cap permits it."""
    last = state["messages"][-1]
    needs_rag = isinstance(last, AIMessage) and bool(last.tool_calls)
    return "rag_tool" if needs_rag and state.get("tool_loops", 0) < MAX_TOOL_LOOPS else END


def route_initial_request(state: AgentState) -> str:
    """Use direct retrieval only for an unambiguous fresh visitor question."""
    text = _latest_user_text(state)
    if should_direct_route(text):
        return "direct_route"
    return "direct_rag" if should_direct_rag(text) else "llm_think"


def build_agent_graph(with_checkpointer: bool = True):
    """Compile the graph for CLI chat or LangGraph Studio.

    Studio/Agent Server owns persistence itself and rejects a custom checkpointer;
    the command-line ``chat`` helper retains MemorySaver for local conversations.
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("llm_think", llm_think_node)
    workflow.add_node("rag_tool", rag_tool_node)
    workflow.add_node("direct_rag", direct_rag_node)
    workflow.add_node("direct_route", direct_route_node)
    workflow.add_conditional_edges(
        START,
        route_initial_request,
        {"direct_rag": "direct_rag", "direct_route": "direct_route", "llm_think": "llm_think"},
    )
    workflow.add_edge("direct_rag", "llm_think")
    workflow.add_edge("direct_route", END)
    workflow.add_conditional_edges("llm_think", route_after_llm, {"rag_tool": "rag_tool", END: END})
    workflow.add_edge("rag_tool", "llm_think")
    return workflow.compile(checkpointer=MemorySaver()) if with_checkpointer else workflow.compile()


agent_graph = build_agent_graph()
# Exported separately for ``langgraph dev``; do not attach MemorySaver here.
studio_agent_graph = build_agent_graph(with_checkpointer=False)


def chat(user_text: str, thread_id: str = "default") -> str:
    """Chat while retaining short-term history for the same thread_id."""
    result = agent_graph.invoke(
        {
            "messages": [("user", user_text)],
            "tool_loops": 0,
            "retrieved_evidence": [],
            "performance_metrics": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content


def chat_with_profile(user_text: str, thread_id: str = "profile") -> tuple[str, list[dict[str, Any]]]:
    """Run one chat request and return the answer plus node-by-node timings."""
    result = agent_graph.invoke(
        {
            "messages": [("user", user_text)],
            "tool_loops": 0,
            "retrieved_evidence": [],
            "performance_metrics": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content, result.get("performance_metrics", [])


if __name__ == "__main__":
    # 测试入口：固定问题覆盖“模型思考→条件路由→模拟 RAG→最终回答”链路。
    # 该测试会请求 DeepSeek API；密钥始终从环境变量读取，不写入代码。
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("请先设置 DEEPSEEK_API_KEY，再运行测试。")

    sample_questions = [
        "陈家祠是什么时候建成的？",
        "陈家祠开放到几点？",
        "陈家祠有哪些值得参观的设施和特色？",
    ]
    print("开始执行陈家祠 Agent 测试样例：")
    for index, question in enumerate(sample_questions, start=1):
        # 每个样例使用独立会话，避免上一题的上下文影响本题检索判断。
        answer = chat(question, thread_id=f"sample-{index}")
        print(f"\n[样例 {index}] 游客：{question}\n助手：{answer}")

    # 样例完成后进入交互模式；同一默认 thread_id 自动保留短期会话记忆。
    print("Chen Clan Academy assistant. Type exit to quit.")
    while True:
        question = input("You: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if question:
            print(f"Assistant: {chat(question)}")
