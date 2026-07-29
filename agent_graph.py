"""Guangzhou Chen Clan Academy Agent backed by local Chinese hybrid RAG."""

from __future__ import annotations

import os
import json
import time
from dataclasses import asdict
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
from duration_parser import has_route_duration_context, parse_duration_minutes
from rag_retrieval import ChenClanHybridRetriever
from route_planner import CATALOG_FILE, recommend_route, _read_catalog
from tour_navigation import (
    format_next_stop_navigation,
    next_stop_navigation,
)
from tour_interaction import handle_tour_event, initialize_interaction
from tour_intent import classify_tour_intent
from tour_presenter import present_clarification, present_tour_event, present_tour_state
from tour_state import start_tour
from tour_qa import (
    CRAFT_TERMS,
    answer_qa_follow_up_detail,
    answer_tour_question,
    build_qa_context_from_answer,
    is_point_inventory_request,
)
from craft_knowledge import parse_craft_explanation_request
from qa_context import (
    clear_qa_context,
    is_qa_follow_up_detail_request,
    is_qa_subject_follow_up_request,
)
from narration_coverage import empty_narration_coverage
from narration_coverage import IntroductionRecord, NarrationCoverageError, commit_introductions, load_narration_coverage
from term_card_runtime import is_explicit_term_question
from research_card_retrieval import is_explicit_research_question
from comparison_retrieval import is_explicit_comparison_question
from photo_spot_runtime import is_explicit_photo_request, is_unsafe_photo_request
from semantic_normalization import canonical_control_text, recognize_semantic_candidate
from guide_program_evidence import build_stop_guidance, reexpress_current_stop_guidance
from profile_dialogue import collect_profile_input
from profile_update import apply_profile_update, is_profile_update_request
from extended_profile_control import apply_extended_profile_control, parse_extended_profile_control
from visitor_profile import VisitorProfileError, create_visitor_profile, profile_from_dict
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
    tour_state: dict[str, Any]
    tour_interaction_state: dict[str, Any]
    tour_presentation: dict[str, Any]
    last_tour_intent: dict[str, Any]
    last_tour_event: dict[str, Any]
    active_stop_program: dict[str, Any]
    active_guidance_evidence_by_item: dict[str, list[dict[str, Any]]]
    # E5-A1 thread-local introduction coverage.  It is deliberately separate
    # from TourState, VisitorProfile, qa_context and the active StopProgram.
    narration_coverage: dict[str, Any]
    active_guidance_evidence_bundle: dict[str, Any]
    active_narration_render_audit: dict[str, Any]
    qa_context: dict[str, Any]
    # C2 preferences are distinct from TourState's per-tour snapshot.  C3
    # will explicitly copy a validated profile when a route is initialized.
    visitor_profile: dict[str, Any]
    profile_collection: dict[str, Any]
    last_profile_update: dict[str, Any]
    last_extended_profile_control: dict[str, Any]
    # Per-turn, auditable input normalization.  This is not TourState or a
    # VisitorProfile: it is reset on every user message and can only map into
    # existing deterministic control parsers.
    semantic_candidate: dict[str, Any] | None
    semantic_control_text: str | None


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
    route_terms = ("路线", "规划", "怎么逛", "游览", "参观顺序", "导览", "带我逛")
    return any(term in user_text for term in route_terms) or has_route_duration_context(user_text)


def _route_request_from_text(user_text: str) -> tuple[int, list[str]]:
    duration = parse_duration_minutes(user_text)
    if duration.reason_code == "ambiguous_duration":
        raise VisitorProfileError("时间表达包含多个不同分钟数，请只确认一个可用时间。")
    minutes = duration.minutes if duration.ok else 30
    interests = [
        term
        for term in ("灰塑", "木雕", "石雕", "陶塑", "三国", "故事", "吉祥", "工艺", "建筑装饰", "深度")
        if term in user_text
    ]
    return minutes, interests


def _latest_user_text(state: AgentState) -> str:
    """Return the current visitor message when routing a fresh graph turn."""
    if not state.get("messages"):
        return ""
    content = state["messages"][-1].content
    return content if isinstance(content, str) else str(content)


def _effective_control_text(state: AgentState) -> str:
    """Return a bounded canonical control phrase, otherwise the raw message.

    The raw message remains the sole input for RAG and presentation.  Only
    control routing may consume this field, after the semantic candidate has
    been validated and converted into vocabulary the existing parser owns.
    """
    normalized = state.get("semantic_control_text")
    return normalized if isinstance(normalized, str) and normalized else _latest_user_text(state)


def _invoke_semantic_model(prompt: str) -> str:
    """Use the configured model only as a schema-bounded recognizer."""
    response = build_model(with_tools=False).invoke([
        {"role": "system", "content": "只执行受控语义分类；不得回答用户。"},
        {"role": "user", "content": prompt},
    ])
    return response.content if isinstance(response.content, str) else str(response.content)


def semantic_normalization_node(state: AgentState) -> dict[str, Any]:
    """Propose a safe synonym normalization without executing any operation."""
    started = time.perf_counter()
    raw_text = _latest_user_text(state)
    decision = classify_tour_intent(
        raw_text, state.get("tour_state"), state.get("tour_interaction_state")
    )
    # Existing deterministic controls have precedence.  Safety is also kept
    # entirely outside the model path.  A model is queried only when the
    # current grammar has no control interpretation at all.
    if not raw_text or decision.route_kind != "other" or is_unsafe_photo_request(raw_text):
        return {
            "semantic_candidate": None,
            "semantic_control_text": None,
            "performance_metrics": _append_metric(
                state, "semantic_normalization", time.perf_counter() - started,
                status="not_needed",
            ),
        }
    candidate = recognize_semantic_candidate(raw_text, _invoke_semantic_model)
    canonical = canonical_control_text(candidate)
    return {
        "semantic_candidate": candidate.to_dict() if candidate.actionable else None,
        "semantic_control_text": canonical,
        "performance_metrics": _append_metric(
            state, "semantic_normalization", time.perf_counter() - started,
            status="candidate" if canonical else "no_actionable_candidate",
            candidate_kind=candidate.candidate_kind,
        ),
    }


def _last_assistant_response_kind(state: AgentState) -> str | None:
    """Inspect message metadata only; it never infers tour facts from prose."""
    for message in reversed(state.get("messages", [])[:-1]):
        if not isinstance(message, AIMessage):
            continue
        metadata = message.additional_kwargs or {}
        if metadata.get("tour_qa_answer"):
            return "tour_qa"
        if metadata.get("stop_guidance"):
            return "stop_guidance"
        return "other"
    return None


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
        # A generic LLM turn is a non-question conversational turn from the
        # perspective of the bounded tour-QA follow-up contract.  It must not
        # leave an earlier local query eligible for a later omitted follow-up.
        "qa_context": clear_qa_context(state.get("qa_context")),
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
    started = time.perf_counter()
    # C3 consumes the already validated C1/C2 profile.  The legacy fallback
    # preserves safe direct calls used by existing scripts and tests; it does
    # not create a second persistent profile store.
    try:
        if state.get("visitor_profile"):
            profile = profile_from_dict(state["visitor_profile"])
            profile_source = "visitor_profile"
        else:
            minutes, interests = _route_request_from_text(query)
            profile = create_visitor_profile(
                available_minutes=minutes, interests=interests, detail_level="standard"
            )
            profile_source = "legacy_text_fallback"
    except VisitorProfileError as exc:
        return {
            "messages": [AIMessage(content=f"游客画像无效，无法开始路线：{exc}")],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "performance_metrics": _append_metric(
                state, "direct_route", time.perf_counter() - started,
                route_started=False, profile_error=True,
            ),
        }
    minutes = profile.available_minutes
    interests = list(profile.interests)
    try:
        selection_result = recommend_route(
            available_minutes=minutes,
            interests=interests,
            detail_level=profile.detail_level,
        )
        if selection_result.selected is None:
            return {
                "messages": [AIMessage(content=(
                    "当前时间预算内没有可安全安排的审核路线；请增加可用时间或调整需求。"
                ))],
                "qa_context": clear_qa_context(state.get("qa_context")),
                "performance_metrics": _append_metric(
                    state, "direct_route", time.perf_counter() - started,
                    route_started=False, route_error=True,
                    route_selection_status=selection_result.status,
                    reason_code=selection_result.reason_code,
                ),
            }
        plan = selection_result.selected
        route_id = plan.route_id
        route_strategy = plan.route_strategy
        plan_data = plan.to_dict()
        guide_stop_ids = plan.guide_stop_ids
        explanation_seconds = plan.estimated_explanation_seconds
        observation_seconds = plan.estimated_observation_seconds
        interaction_seconds = plan.estimated_interaction_seconds
        total_seconds = plan.estimated_total_seconds
        walk_seconds = plan.estimated_walk_seconds
        exit_node_id = plan.exit_node_id
        exit_return_seconds = plan.estimated_exit_return_seconds
    except (ValueError, RuntimeError) as exc:
        return {
            "messages": [AIMessage(content=f"无法按当前画像生成审核路线：{exc}")],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "performance_metrics": _append_metric(
                state, "direct_route", time.perf_counter() - started,
                route_started=False, route_error=True,
            ),
        }
    catalog = _read_catalog(CATALOG_FILE)
    tour = start_tour(plan, interests=interests, detail_level=profile.detail_level)
    interaction = initialize_interaction(tour)
    stop_lines = []
    for index, node_id in enumerate(guide_stop_ids, start=1):
        card = catalog[node_id]
        stop_lines.append(
            f"{index}. {card['stop_name']}：{card['guide_focus']}"
        )
    total_minutes = total_seconds / 60
    message = (
        f"为您推荐“{plan.display_name}”。预计总时长约 {total_minutes:.0f} 分钟"
        f"（可用时间 {minutes} 分钟；策略：{'人工审核锚点' if route_strategy == 'anchor' else '动态组合'}）。\n\n"
        "讲解停留顺序：\n"
        + "\n".join(stop_lines)
        + "\n\n"
        f"路线会经过 {len(plan.full_path_node_ids)} 个已审核空间节点、"
        f"使用 {len(plan.edge_ids)} 条已审核双向边。"
        f"时间包含讲解 {explanation_seconds // 60} 分钟、"
        f"观察 {observation_seconds // 60} 分钟、"
        f"互动 {interaction_seconds // 60} 分钟和步行约 {walk_seconds} 秒。\n"
        f"结束后将沿已审核路径回到前院出口区（{exit_node_id}），已预留约 {exit_return_seconds} 秒。\n\n"
        "提示：步行时间基于官网地图与已审核路线估算，现场通行、驻足和开放情况请以馆方安排为准。"
        "\n\n"
        + format_next_stop_navigation(next_stop_navigation(tour))
    )
    marker = AIMessage(content=message, additional_kwargs={"direct_route_plan": True})
    presentation = present_tour_state(tour, interaction)
    return {
        "messages": [marker],
        "selected_route_id": route_id,
        "active_route_plan": plan_data,
        "tour_state": tour,
        "tour_interaction_state": interaction,
        "tour_presentation": presentation,
        "visitor_profile": profile.to_dict(),
        # A route initialization starts a new tour session, so successful
        # introductions from an earlier route must not suppress first-contact
        # narration in this one.  E5-A4 will be the only later writer.
        "narration_coverage": empty_narration_coverage().to_dict(),
        "active_guidance_evidence_bundle": None,
        "active_narration_render_audit": None,
        "qa_context": clear_qa_context(state.get("qa_context")),
        "performance_metrics": _append_metric(
            state,
            "direct_route",
            time.perf_counter() - started,
            route_id=route_id,
            route_strategy=route_strategy,
            requested_minutes=minutes,
            interests=interests,
            detail_level=profile.detail_level,
            profile_source=profile_source,
            route_selection_reason=plan.selection_reason,
        ),
    }


def profile_collection_node(state: AgentState) -> dict[str, Any]:
    """Collect explicit C2 preferences without starting or changing a tour."""
    query = _effective_control_text(state)
    decision = classify_tour_intent(
        query, state.get("tour_state"), state.get("tour_interaction_state")
    )
    start_collection = decision.route_kind == "route_request" or should_direct_route(query)
    started = time.perf_counter()
    result = collect_profile_input(
        state.get("profile_collection"), query, start_collection=start_collection,
        base_profile=state.get("visitor_profile"),
    )
    if result is None:
        # The router should only enter this node for a route request or an
        # active non-question collection turn.  Keep an explicit safe reply
        # in case a future routing rule violates that boundary.
        message = "请先说明您想规划路线，或继续回答当前的导览偏好问题。"
        return {
            "messages": [AIMessage(content=message)],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "performance_metrics": _append_metric(
                state, "profile_collection", time.perf_counter() - started,
                status="ignored",
            ),
        }
    payload = result.to_dict()
    return {
        "messages": [AIMessage(content=payload["message"])],
        "qa_context": clear_qa_context(state.get("qa_context")),
        "visitor_profile": payload["visitor_profile"],
        "profile_collection": payload["profile_collection"],
        "performance_metrics": _append_metric(
            state, "profile_collection", time.perf_counter() - started,
            status=payload["status"], reason_code=payload["reason_code"],
            resolved_fields=payload["profile_collection"]["resolved_fields"],
        ),
    }


def profile_update_node(state: AgentState) -> dict[str, Any]:
    """Apply a C4 preference update without allowing an LLM to write state."""
    query = _effective_control_text(state)
    started = time.perf_counter()
    intent = classify_tour_intent(
        query, state.get("tour_state"), state.get("tour_interaction_state")
    )
    # A control operation plus an update must be split into two turns.  This
    # prevents, for example, "我到了月台，后面简单讲" from recording only the
    # preference half of a multi-intent command.
    if intent.route_kind == "tour_event" and intent.event_type != "replan_time":
        message = "请先完成到达、跳过或确认等当前导览操作；调整后续偏好请单独发送。"
        presentation = present_clarification(message, state.get("tour_interaction_state"))
        return {
            "messages": [AIMessage(content=message)],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "tour_presentation": presentation,
            "last_profile_update": {"ok": False, "code": "multiple_intents"},
            "performance_metrics": _append_metric(
                state, "profile_update", time.perf_counter() - started,
                ok=False, code="multiple_intents",
            ),
        }
    if intent.route_kind == "clarification" and intent.reason_code == "multiple_intents":
        presentation = present_clarification(intent.clarification_message or "请一次只调整一项导览操作。", state.get("tour_interaction_state"))
        return {
            "messages": [AIMessage(content=presentation["message"])],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "tour_presentation": presentation,
            "last_profile_update": {"ok": False, "code": "multiple_intents"},
            "performance_metrics": _append_metric(
                state, "profile_update", time.perf_counter() - started,
                ok=False, code="multiple_intents",
            ),
        }
    result = apply_profile_update(
        state.get("visitor_profile"), state.get("tour_state"),
        state.get("tour_interaction_state"), query,
    )
    if result["ok"]:
        presentation = present_tour_state(
            result["tour_state"], result["interaction_state"], message=result["message"]
        )
        presentation = {**presentation, "code": result["code"], "ok": True}
    else:
        presentation = present_clarification(result["message"], result.get("interaction_state"))
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=presentation["message"])],
        "last_profile_update": {"ok": result["ok"], "code": result["code"]},
        "tour_presentation": presentation,
        "qa_context": clear_qa_context(state.get("qa_context")),
        "performance_metrics": _append_metric(
            state, "profile_update", time.perf_counter() - started,
            ok=result["ok"], code=result["code"],
        ),
    }
    if result["ok"]:
        updates["visitor_profile"] = result["visitor_profile"]
        updates["tour_state"] = result["tour_state"]
        updates["tour_interaction_state"] = result["interaction_state"]
        plan = result["data"].get("plan")
        if plan:
            updates["active_route_plan"] = {**asdict(plan), "route_strategy": "replanned"}
            updates["selected_route_id"] = plan.route_id
    return updates


def extended_profile_control_node(state: AgentState) -> dict[str, Any]:
    """Apply only explicit C8 controls; it never writes TourState."""
    started = time.perf_counter()
    result = apply_extended_profile_control(state.get("visitor_profile"), _latest_user_text(state))
    control = result["control"]
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result["message"])],
        "qa_context": clear_qa_context(state.get("qa_context")),
        "last_extended_profile_control": {"ok": result["ok"], "kind": control.kind, "patch": control.patch},
        "performance_metrics": _append_metric(state, "extended_profile_control", time.perf_counter() - started,
                                                ok=result["ok"], kind=control.kind),
    }
    if not result["ok"]:
        return updates
    if control.kind == "delete":
        updates["visitor_profile"] = None
        updates["profile_collection"] = None
        return updates
    if control.kind != "view":
        if control.reexpress_current:
            rewritten = reexpress_current_stop_guidance(
                state.get("tour_state"), state.get("tour_interaction_state"),
                state.get("active_stop_program"), state.get("active_guidance_evidence_by_item"), result["profile"],
            )
            # Explicit re-expression is transactional: do not retain a new
            # preference if the requested current-stop rendering is impossible.
            if not rewritten["ok"]:
                updates["messages"] = [AIMessage(content=rewritten["message"])]
                updates["last_extended_profile_control"] = {"ok": False, "kind": control.kind, "code": "reexpress_unavailable"}
                return updates
            updates.update({
                "visitor_profile": result["profile"], "active_stop_program": rewritten["stop_program"],
                "active_guidance_evidence_by_item": rewritten["evidence_by_item"],
                "retrieved_evidence": rewritten["evidence"], "tour_presentation": rewritten["presentation"],
                "messages": [AIMessage(content=rewritten["message"], additional_kwargs={"stop_guidance": True, "reexpressed": True})],
            })
            return updates
        updates["visitor_profile"] = result["profile"]
    return updates


def tour_event_node(state: AgentState) -> dict[str, Any]:
    """Execute one already-classified tour event only through A1-1 adapter."""
    started = time.perf_counter()
    decision = classify_tour_intent(
        _effective_control_text(state), state.get("tour_state"), state.get("tour_interaction_state")
    )
    if decision.route_kind != "tour_event" or not decision.event_type:
        return {
            "messages": [AIMessage(content="我无法确认这项导游操作，请换一种明确说法。")],
            "qa_context": clear_qa_context(state.get("qa_context")),
            "last_tour_intent": decision.to_dict(),
            "performance_metrics": _append_metric(state, "tour_event", time.perf_counter() - started, executed=False),
        }
    result = handle_tour_event(
        state.get("tour_state"),
        state.get("tour_interaction_state"),
        decision.event_type,
        **(decision.arguments or {}),
    )
    presentation = present_tour_event(result)
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=presentation["message"])],
        "last_tour_intent": decision.to_dict(),
        "last_tour_event": {
            "event": result["event"],
            "code": result["code"],
            "ok": result["ok"],
        },
        "tour_presentation": presentation,
        "qa_context": clear_qa_context(state.get("qa_context")),
        "performance_metrics": _append_metric(
            state,
            "tour_event",
            time.perf_counter() - started,
            event_type=decision.event_type,
            event_code=result["code"],
            ok=result["ok"],
        ),
    }
    if result["tour_state"] is not None:
        updates["tour_state"] = result["tour_state"]
    if result["interaction_state"] is not None:
        updates["tour_interaction_state"] = result["interaction_state"]
    plan = result["data"].get("plan")
    if plan:
        updates["active_route_plan"] = {**asdict(plan), "route_strategy": "replanned"}
        updates["selected_route_id"] = plan.route_id
    return updates


def stop_guidance_node(state: AgentState) -> dict[str, Any]:
    """Generate sourced current-stop guidance without advancing TourState."""
    started = time.perf_counter()
    last_event = state.get("last_tour_event", {})
    result = build_stop_guidance(
        state.get("tour_state"),
        state.get("tour_interaction_state"),
        lambda retrieval_query: str(chen_clan_academy_rag_search.invoke({"query": retrieval_query})),
        current_program=state.get("active_stop_program"),
        detailed=last_event.get("event") == "request_stop_detail",
        visitor_profile=state.get("visitor_profile"),
        narration_coverage=state.get("narration_coverage"),
    )
    coverage_before = load_narration_coverage(state.get("narration_coverage"))
    coverage_after = coverage_before
    commit_audit: dict[str, Any] = {"status": "not_attempted", "submitted_subject_ids": [], "committed_subject_ids": []}
    if result.get("status") == "guided_e5":
        render_audit = result.get("narration_render_audit") or {}
        current_node = (state.get("tour_state") or {}).get("current_stop_id")
        rendered = {
            ("craft", subject_id) for subject_id in render_audit.get("rendered_craft_ids", [])
        }.union({("ornament", subject_id) for subject_id in render_audit.get("rendered_ornament_ids", [])})
        used_source_ids = set(render_audit.get("used_source_ids", []))
        turn_id = f"stop_guidance:{current_node}:{len(state.get('messages', [])) + 1}"
        try:
            records: list[IntroductionRecord] = []
            for candidate in result.get("coverage_candidates", []):
                if not isinstance(candidate, dict):
                    continue
                key = (candidate.get("subject_kind"), candidate.get("subject_id"))
                expected_evidence_kind = {
                    "craft": "craft_overview",
                    "ornament": "ornament_detail",
                }.get(key[0])
                actual_sources = tuple(source for source in candidate.get("source_ids", []) if source in used_source_ids)
                if (
                    key not in rendered
                    or candidate.get("evidence_kind") != expected_evidence_kind
                    or not actual_sources
                    or not result.get("message", "").strip()
                    or candidate.get("node_id") != current_node
                    or current_node != render_audit.get("node_id")
                ):
                    continue
                records.append(IntroductionRecord(
                    subject_kind=key[0], subject_id=key[1], source_ids=actual_sources,
                    introduced_by="stop_guidance", node_id=current_node, turn_id=turn_id,
                ))
            coverage_after = commit_introductions(coverage_before, records)
            commit_audit = {
                "status": "committed" if records else "no_eligible_candidates",
                "submitted_subject_ids": [record.subject_id for record in records],
                "committed_subject_ids": list(coverage_after.introduced_craft_ids) + list(coverage_after.introduced_ornament_ids),
                "turn_id": turn_id,
            }
        except (NarrationCoverageError, TypeError, ValueError):
            # Atomic failure: retain the exact original coverage snapshot.
            coverage_after = coverage_before
            commit_audit = {"status": "atomic_commit_rejected", "submitted_subject_ids": [], "committed_subject_ids": []}
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result["message"], additional_kwargs={"stop_guidance": True})],
        "retrieved_evidence": result["evidence"],
        "tour_presentation": result["presentation"],
        "narration_coverage": coverage_after.to_dict(),
        "performance_metrics": _append_metric(
            state,
            "stop_guidance",
            time.perf_counter() - started,
            status=result["status"],
            evidence_count=len(result["evidence"]),
            selected_item_count=len((result.get("stop_program") or {}).get("selected_items", [])),
        ),
    }
    if result["stop_program"] is not None:
        updates["active_stop_program"] = result["stop_program"]
        updates["active_guidance_evidence_by_item"] = result.get("evidence_by_item", {})
    if result.get("guidance_evidence_bundle_audit") is not None:
        updates["active_guidance_evidence_bundle"] = result["guidance_evidence_bundle_audit"]
    if result.get("narration_render_audit") is not None:
        updates["active_narration_render_audit"] = {
            **result["narration_render_audit"],
            "coverage_commit": commit_audit,
        }
    # Deliberately do not return tour_state or tour_interaction_state.  The
    # A1 adapter remains the only mutation entry point.
    return updates


def clarification_node(state: AgentState) -> dict[str, Any]:
    """Reply to low-confidence or multi-intent text without changing TourState."""
    decision = classify_tour_intent(
        _effective_control_text(state), state.get("tour_state"), state.get("tour_interaction_state")
    )
    presentation = present_clarification(
        decision.clarification_message or "请换一种更明确的说法。",
        state.get("tour_interaction_state"),
    )
    return {
        "messages": [AIMessage(content=presentation["message"])],
        "last_tour_intent": decision.to_dict(),
        "tour_presentation": presentation,
        "qa_context": clear_qa_context(state.get("qa_context")),
        "performance_metrics": _append_metric(state, "clarification", 0.0, reason_code=decision.reason_code),
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
        "qa_context": clear_qa_context(state.get("qa_context")),
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


def tour_qa_node(state: AgentState) -> dict[str, Any]:
    """Answer a factual question with active-tour context but no state mutation.

    Retrieval still uses the existing ``chen_clan_academy_rag_search`` tool.
    ``tour_qa`` only supplies reviewed point metadata as a query hint and restores
    the A1 action protocol after evidence is returned.
    """
    query = _latest_user_text(state)
    started = time.perf_counter()
    result = answer_tour_question(
        query,
        state.get("tour_state"),
        state.get("tour_interaction_state"),
        lambda retrieval_query: str(chen_clan_academy_rag_search.invoke({"query": retrieval_query})),
        state.get("visitor_profile"),
    )
    updates: dict[str, Any] = {
        "messages": [AIMessage(content=result["message"], additional_kwargs={"tour_qa_answer": True})],
        "retrieved_evidence": result["evidence"],
        "performance_metrics": _append_metric(
            state,
            "tour_qa",
            time.perf_counter() - started,
            evidence_count=len(result["evidence"]),
            current_stop_id=(result.get("point_context") or {}).get("node_id"),
        ),
        "qa_context": build_qa_context_from_answer(
            query, result, state.get("tour_state")
        ) or clear_qa_context(state.get("qa_context")),
    }
    # The presenter is UI data, not a state transition.  Deliberately do not
    # return tour_state or tour_interaction_state here.
    if result["presentation"] is not None:
        updates["tour_presentation"] = result["presentation"]
    return updates


def qa_follow_up_detail_node(state: AgentState) -> dict[str, Any]:
    """Expand only the immediately preceding bounded tour-QA context."""
    query = _latest_user_text(state)
    started = time.perf_counter()
    result = answer_qa_follow_up_detail(
        query,
        state.get("qa_context"),
        state.get("tour_state"),
        state.get("tour_interaction_state"),
        lambda retrieval_query: str(chen_clan_academy_rag_search.invoke({"query": retrieval_query})),
        detailed=is_qa_follow_up_detail_request(query),
    )
    updated_context = build_qa_context_from_answer(
        query, result, state.get("tour_state"), state.get("qa_context")
    )
    updates: dict[str, Any] = {
        "messages": [AIMessage(
            content=result["message"],
            additional_kwargs={"tour_qa_answer": True, "qa_follow_up_detail": True},
        )],
        "retrieved_evidence": result["evidence"],
        "qa_context": updated_context or clear_qa_context(state.get("qa_context")),
        "performance_metrics": _append_metric(
            state,
            "qa_follow_up_detail",
            time.perf_counter() - started,
            mode=result.get("mode"),
            evidence_count=len(result["evidence"]),
        ),
    }
    if result.get("presentation") is not None:
        updates["tour_presentation"] = result["presentation"]
    return updates


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
    """Apply A1-2 priority before route/RAG/LLM fallbacks."""
    raw_text = _latest_user_text(state)
    text = _effective_control_text(state)
    # Safety is evaluated before event/multi-intent arbitration.  A dangerous
    # photo request must never record an arrival first or reach D5 candidates.
    # The D6 handler performs the deterministic refusal without state writes.
    if is_unsafe_photo_request(raw_text):
        return "tour_qa"
    # All seven generic craft explanations use one deterministic, evidence-
    # backed path before generic RAG or LLM routing.  The parser is anchored,
    # so comparisons and concrete ornament/story questions remain with their
    # existing handlers.
    if parse_craft_explanation_request(raw_text):
        return "tour_qa"
    # A1 reserves request_stop_detail for the active physical StopProgram.
    # The same wording may instead follow a successful knowledge answer; that
    # read-only path is selected only from explicit message metadata.
    if is_qa_follow_up_detail_request(raw_text) or is_qa_subject_follow_up_request(raw_text):
        # A craft named in this turn is a complete question, not an omitted
        # subject that depends on the previous QA response.  This keeps
        # “请详细讲讲灰塑” usable before any route has started.
        if any(craft in raw_text for craft in CRAFT_TERMS):
            return "tour_qa"
        previous_kind = _last_assistant_response_kind(state)
        if previous_kind == "tour_qa":
            return "qa_follow_up_detail"
        if previous_kind not in {"stop_guidance"}:
            return "qa_follow_up_detail"
    decision = classify_tour_intent(
        text, state.get("tour_state"), state.get("tour_interaction_state")
    )
    extended = parse_extended_profile_control(raw_text)
    # A physical tour event and a preference change are separate atomic turns;
    # never let the preference half silently suppress arrival/skip semantics.
    if extended.kind != "none" and decision.route_kind in {"tour_event", "clarification"}:
        return "clarification"
    if extended.kind != "none":
        return "extended_profile_control"
    if decision.route_kind == "tour_event":
        if is_profile_update_request(text):
            return "profile_update"
        return "tour_event"
    if decision.route_kind == "clarification":
        if is_profile_update_request(text):
            return "profile_update"
        return "clarification"
    if state.get("tour_state") and state.get("tour_interaction_state") and is_profile_update_request(text):
        return "profile_update"
    # D6 photo handling retains priority because a mixed photo/route request
    # must receive its existing no-partial-mutation clarification.  By
    # contrast, a genuine route action may contain comparison or research
    # words as *planning preferences* (for example, “一小时，想看三国工艺
    # 比较，请规划路线”).  Do not let those words divert a route request into
    # D3/D4 knowledge Q&A before C2 can collect the route profile.
    if is_explicit_photo_request(raw_text):
        return "tour_qa"
    if decision.route_kind == "route_request" or should_direct_route(text):
        return "profile_collection"
    # D3/D4 are deterministic sub-routes of tour_qa.  They are checked after
    # all event/profile controls and explicit route actions, but before generic
    # RAG/LLM fallbacks.
    if is_explicit_comparison_question(text) or is_explicit_research_question(text):
        return "tour_qa"
    # C2 collects only explicit preferences before C3 later consumes them for
    # route selection. Control events and factual questions retain priority.
    profile_turn = collect_profile_input(state.get("profile_collection"), text)
    if profile_turn is not None:
        return "profile_collection"
    if decision.route_kind == "rag_question" or should_direct_rag(text):
        # An explicit audited point inventory is structured data even before a
        # route starts. Other no-route facts retain the established RAG path.
        if is_point_inventory_request(raw_text, state.get("tour_state")) or is_explicit_photo_request(raw_text) or is_explicit_comparison_question(raw_text) or is_explicit_research_question(raw_text) or is_explicit_term_question(raw_text):
            return "tour_qa"
        return "tour_qa" if state.get("tour_state") and state.get("tour_interaction_state") else "direct_rag"
    return "llm_think"


def route_after_profile_collection(state: AgentState) -> str:
    """Start a route only after C2 has produced a complete validated profile."""
    collection = state.get("profile_collection") or {}
    return "direct_route" if collection.get("status") == "ready" else END


def route_after_tour_event(state: AgentState) -> str:
    """Send only successful arrival/detail events into B3 evidence guidance."""
    event = state.get("last_tour_event", {})
    if event.get("ok") and (
        (event.get("event") == "arrive_at_stop" and event.get("code") == "arrived")
        or (event.get("event") == "request_stop_detail" and event.get("code") == "detail_requested")
    ):
        return "stop_guidance"
    return END


def build_agent_graph(with_checkpointer: bool = True):
    """Compile the graph for CLI chat or LangGraph Studio.

    Studio/Agent Server owns persistence itself and rejects a custom checkpointer;
    the command-line ``chat`` helper retains MemorySaver for local conversations.
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("semantic_normalization", semantic_normalization_node)
    workflow.add_node("llm_think", llm_think_node)
    workflow.add_node("rag_tool", rag_tool_node)
    workflow.add_node("direct_rag", direct_rag_node)
    workflow.add_node("tour_qa", tour_qa_node)
    workflow.add_node("qa_follow_up_detail", qa_follow_up_detail_node)
    workflow.add_node("direct_route", direct_route_node)
    workflow.add_node("profile_collection", profile_collection_node)
    workflow.add_node("profile_update", profile_update_node)
    workflow.add_node("extended_profile_control", extended_profile_control_node)
    workflow.add_node("tour_event", tour_event_node)
    workflow.add_node("stop_guidance", stop_guidance_node)
    workflow.add_node("clarification", clarification_node)
    workflow.add_edge(START, "semantic_normalization")
    workflow.add_conditional_edges(
        "semantic_normalization",
        route_initial_request,
        {
            "direct_rag": "direct_rag", "tour_qa": "tour_qa", "qa_follow_up_detail": "qa_follow_up_detail", "direct_route": "direct_route", "profile_collection": "profile_collection", "profile_update": "profile_update", "extended_profile_control": "extended_profile_control", "tour_event": "tour_event",
            "clarification": "clarification", "llm_think": "llm_think",
        },
    )
    workflow.add_edge("direct_rag", "llm_think")
    workflow.add_edge("tour_qa", END)
    workflow.add_edge("qa_follow_up_detail", END)
    workflow.add_edge("direct_route", END)
    workflow.add_conditional_edges(
        "profile_collection", route_after_profile_collection,
        {"direct_route": "direct_route", END: END},
    )
    workflow.add_edge("profile_update", END)
    workflow.add_edge("extended_profile_control", END)
    workflow.add_conditional_edges("tour_event", route_after_tour_event, {"stop_guidance": "stop_guidance", END: END})
    workflow.add_edge("stop_guidance", END)
    workflow.add_edge("clarification", END)
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
