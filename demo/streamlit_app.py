"""Competition-facing Streamlit shell using public messages from one Agent turn."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.demo_adapter import DemoAdapter


LOGGER = logging.getLogger(__name__)

STYLES = {
    "中性清晰": "neutral",
    "儿童友好": "child",
    "亲子共游": "family",
    "研学观察": "student_research",
    "专业讲解": "professional",
    "静听模式": "listen_only",
    "混合群体": "mixed_group",
    "霸道总裁": "dominant_ceo",
    "奶气学弟": "cute_junior",
    "古风书生": "ancient_scholar",
    "知心姐姐": "warm_sister",
    "闺蜜唠嗑": "bestie_chat",
    "兄弟搭子": "buddy_guide",
    "探秘闯关": "exploration_game",
    "打卡出片": "photo_guide",
    "祠中宿生": "hostel_scholar",
    "西关少爷（粤语）": "xiguan_young_master",
    "粤派讲古（粤语）": "cantonese_storyteller",
}
INTERESTS = ["灰塑", "木雕", "石雕", "陶塑", "故事", "吉祥", "工艺", "建筑装饰"]
QUICK_ACTIONS = ["我到了", "再讲详细一点", "完成本点"]
SCENE_LABELS = {
    "route_planning": "路线规划",
    "welcome": "欢迎来到陈家祠",
    "route_opening": "导览开场",
    "stop_guidance": "当前点讲解",
    "tour_qa": "导览问答",
    "tour_closing": "游览总结",
    "assistant": "导览回复",
}


def _secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def _runtime_setting(name: str, default: str = "") -> str:
    """Prefer this process' explicit rollout setting over deployment Secrets."""
    if name in os.environ:
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _role_rollout_startup_audit(environ: dict[str, str] | None = None) -> dict[str, object]:
    """Return a secret-free audit of the effective role rollout configuration."""
    from controlled_rollout import (
        ROLE_NARRATION,
        ROLE_QA,
        product_capability_policy_from_environment,
        role_runtime_contract,
        rollout_from_environment,
    )

    values = os.environ if environ is None else environ
    rollout = rollout_from_environment(values)
    policy = product_capability_policy_from_environment(values)
    policy_audit = policy.to_audit()
    return {
        "rollout_mode": rollout.mode.value,
        "enabled_capabilities": sorted(rollout.enabled_capabilities),
        "product_policy_enabled": policy.enabled,
        "product_policy_source": policy.source,
        "product_policy_reason_code": policy.reason_code,
        "active_styles": policy_audit["styles"],
        "active_scenes": policy_audit["scenes"],
        "rollout_percentage": policy.rollout_percentage,
        "kill_switch": policy.kill_switch,
        "validation_level": policy.validation_level,
        "fallback_policy": policy.fallback_policy,
        "natural_discourse_enabled": (
            str(values.get("PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED", ""))
            .strip().lower() in {"1", "true", "yes", "on"}
        ),
        "point_role_active_configured": bool(
            rollout.enabled(ROLE_NARRATION)
            and policy.enabled
            and not policy.kill_switch
            and "stop_guidance" in policy.scenes
        ),
        "qa_role_active_configured": bool(
            rollout.enabled(ROLE_QA)
            and policy.enabled
            and not policy.kill_switch
            and {"tour_qa", "qa_follow_up_detail"}.issubset(policy.scenes)
        ),
        "runtime_fingerprint": role_runtime_contract(values)["fingerprint"],
    }


_ROLLOUT_AUDIT_LOGGED = False


def _configure_environment() -> dict[str, object]:
    # API/model Secrets remain deployment-owned and are never rendered or logged.
    for key in (
        "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "ROLE_NARRATION_MODEL",
    ):
        value = _secret(key)
        if value:
            os.environ[key] = value
    # Explicit environment variables win for runtime rollout controls so a
    # local PowerShell acceptance run cannot be silently narrowed by stale
    # Streamlit Secrets. Missing values may still come from deployment Secrets.
    for key in (
        "CJC_READ_ONLY_ROLLOUT_MODE", "CJC_READ_ONLY_ROLLOUT_CAPABILITIES",
        "ROLE_ACTIVE_ENABLED", "ROLE_ACTIVE_STYLES", "ROLE_ACTIVE_SCENES",
        "PRODUCT_ROLE_ACTIVE_ENABLED", "PRODUCT_ROLE_ACTIVE_STYLES",
        "PRODUCT_ROLE_ACTIVE_SCENES", "PRODUCT_ROLE_ROLLOUT_PERCENTAGE",
        "PRODUCT_ROLE_KILL_SWITCH", "PRODUCT_ROLE_VALIDATION_LEVEL",
        "PRODUCT_ROLE_FALLBACK_POLICY",
        "PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED",
        "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED",
    ):
        value = _runtime_setting(key)
        if value:
            os.environ[key] = value
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    audit = _role_rollout_startup_audit()
    global _ROLLOUT_AUDIT_LOGGED
    if not _ROLLOUT_AUDIT_LOGGED:
        LOGGER.info("role_rollout_startup_audit=%s", audit)
        _ROLLOUT_AUDIT_LOGGED = True
    return audit


@st.cache_resource(show_spinner=False)
def _agent_call():
    _configure_environment()
    from agent_graph import chat_public_turn

    return chat_public_turn


@st.cache_resource(show_spinner=False)
def _session_starter():
    _configure_environment()
    from agent_graph import start_public_session

    return start_public_session


def _profile_message(duration: int, interests: list[str], detail: str, style_label: str) -> str:
    interest_text = "、".join(interests) if interests else "岭南建筑装饰"
    return f"中文，定制模式，{duration}分钟，我喜欢{interest_text}，{detail}讲解，选择{style_label}风格"


def _init_adapter() -> DemoAdapter:
    if "demo_adapter" not in st.session_state:
        st.session_state.demo_adapter = DemoAdapter(
            _agent_call(),
            session_starter=_session_starter(),
            max_turns=int(_secret("DEMO_MAX_TURNS", "20")),
            max_input_chars=int(_secret("DEMO_MAX_INPUT_CHARS", "200")),
        )
    return st.session_state.demo_adapter


def _send(adapter: DemoAdapter, message: str) -> None:
    st.session_state.messages.append({"role": "user", "content": message})
    with st.spinner("正在组织本次导览…"):
        reply = adapter.send(message)
    for public_message in reply.messages:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": public_message.text,
                "scene_kind": public_message.scene_kind,
                "service_text": public_message.service_text,
                "error": reply.is_error,
            }
        )
    st.session_state.itinerary = reply.itinerary


def _start_session(adapter: DemoAdapter) -> None:
    reply = adapter.start()
    for public_message in reply.messages:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": public_message.text,
                "scene_kind": public_message.scene_kind,
                "service_text": public_message.service_text,
                "error": reply.is_error,
            }
        )
    st.session_state.itinerary = reply.itinerary


def main() -> None:
    st.set_page_config(page_title="祠语智游｜比赛演示版", page_icon="🏛️", layout="wide")
    _configure_environment()
    st.markdown("""<style>
    .stApp {background:#f7f1e6;color:#23221f;}
    [data-testid='stSidebar']{background:#39251f;}
    [data-testid='stSidebar'] h1,
    [data-testid='stSidebar'] h2,
    [data-testid='stSidebar'] h3,
    [data-testid='stSidebar'] [data-testid='stWidgetLabel'] p,
    [data-testid='stSidebar'] [role='radiogroup'] label p,
    [data-testid='stSidebar'] [data-testid='stCaptionContainer'] p,
    [data-testid='stSidebar'] [data-testid='stSpinner'] p {
        color:#fff8ec !important;
    }
    .hero {padding:1.1rem 1.35rem;border-radius:16px;background:#6f2d26;color:#fff7e8;margin-bottom:1rem;}
    .itinerary {padding:1rem 1.2rem;border:1px solid #c8a55a;border-radius:14px;background:#fffaf0;}
    </style>""", unsafe_allow_html=True)
    st.markdown("<div class='hero'><h1>祠语智游</h1><p>比赛演示版｜根据您的时间、兴趣和当前位置，生成有证据、可推进、可回退的个性化文化导览。</p></div>", unsafe_allow_html=True)

    try:
        adapter = _init_adapter()
    except Exception:
        st.error("Demo配置尚未完成，请检查部署环境后重试。")
        return
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "itinerary" not in st.session_state:
        st.session_state.itinerary = adapter.itinerary
    if not st.session_state.messages:
        _start_session(adapter)

    with st.sidebar:
        st.subheader("开始一段导览")
        style_label = st.selectbox("讲解风格", list(STYLES))
        duration = st.radio("可用时间", [30, 60], horizontal=True, format_func=lambda n: f"{n}分钟")
        interests = st.multiselect("感兴趣的内容", INTERESTS, default=["灰塑"])
        detail = st.radio("讲解节奏", ["标准", "深度"], horizontal=True)
        if st.button("生成我的路线", type="primary", use_container_width=True):
            _send(adapter, _profile_message(duration, interests, detail, style_label))
            st.rerun()
        if st.button("重置会话", use_container_width=True):
            adapter.reset()
            st.session_state.messages = []
            st.session_state.itinerary = adapter.itinerary
            _start_session(adapter)
            st.rerun()
        st.caption("服务状态：可用｜每次对话均由当前导游系统实时处理")

    itinerary = st.session_state.itinerary
    st.markdown(
        f"<div class='itinerary'><b>我的行程</b><br>当前点位：{itinerary.current_stop}　·　下一站：{itinerary.next_stop}<br>"
        f"已完成 {itinerary.completed_count}/{itinerary.total_count} 个讲解点，剩余 {itinerary.remaining_count} 个。</div>",
        unsafe_allow_html=True,
    )
    st.markdown("#### 与导游对话")
    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            if item["role"] == "assistant" and item.get("scene_kind") in SCENE_LABELS:
                st.caption(SCENE_LABELS[item["scene_kind"]])
            st.markdown(item["content"])
            if item["role"] == "assistant" and item.get("service_text"):
                with st.container(border=True):
                    st.caption("下一步提示")
                    st.write(item["service_text"])
    columns = st.columns(3)
    for column, action in zip(columns, QUICK_ACTIONS):
        if column.button(action, use_container_width=True):
            _send(adapter, action)
            st.rerun()
    if prompt := st.chat_input("例如：这里最值得看什么？", max_chars=200):
        _send(adapter, prompt)
        st.rerun()


if __name__ == "__main__":
    main()
