"""Competition-facing Streamlit shell using public messages from one Agent turn."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.demo_adapter import DemoAdapter


STYLES = {
    "中性清晰": "neutral",
    "儿童友好": "child",
    "古风书生": "ancient_scholar",
}
INTERESTS = ["灰塑", "木雕", "石雕", "陶塑", "故事", "吉祥", "工艺", "建筑装饰"]
QUICK_ACTIONS = ["我到了", "再讲详细一点", "完成本点"]


def _secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def _configure_environment() -> None:
    # Secrets take precedence for this process only. They are never rendered or logged.
    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "ROLE_NARRATION_MODEL"):
        value = _secret(key)
        if value:
            os.environ[key] = value
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
    os.environ.setdefault("LANGSMITH_TRACING", "false")


@st.cache_resource(show_spinner=False)
def _agent_call():
    _configure_environment()
    from agent_graph import chat_public_turn

    return chat_public_turn


def _profile_message(duration: int, interests: list[str], detail: str, style_label: str) -> str:
    interest_text = "、".join(interests) if interests else "岭南建筑装饰"
    return f"中文，定制模式，{duration}分钟，我喜欢{interest_text}，{detail}讲解，选择{style_label}风格"


def _init_adapter() -> DemoAdapter:
    if "demo_adapter" not in st.session_state:
        st.session_state.demo_adapter = DemoAdapter(
            _agent_call(),
            max_turns=int(_secret("DEMO_MAX_TURNS", "20")),
            max_input_chars=int(_secret("DEMO_MAX_INPUT_CHARS", "200")),
        )
    return st.session_state.demo_adapter


def _send(adapter: DemoAdapter, message: str) -> None:
    st.session_state.messages.append({"role": "user", "content": message})
    with st.spinner("正在组织本次导览…"):
        reply = adapter.send(message)
    for public_text in reply.messages or (reply.text,):
        st.session_state.messages.append(
            {"role": "assistant", "content": public_text, "error": reply.is_error}
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
            st.write(item["content"])
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
