"""Competition-facing Streamlit shell using public messages from one Agent turn."""

from __future__ import annotations

import os
import sys
import logging
import re
from html import escape
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.demo_adapter import DemoAdapter
from controlled_knowledge_query import OFFICIAL_TICKETING_URL
from duration_parser import parse_duration_minutes


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
JOURNEY_MODES = {
    "经典模式": "classic",
    "定制模式": "custom",
}
CRAFT_INTERESTS = ["灰塑", "木雕", "石雕", "砖雕", "陶塑", "建筑装饰"]
DEFAULT_ROUTE_MINUTES = 60
MIN_ROUTE_MINUTES = 20
MAX_ROUTE_MINUTES = 120
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


def _route_request_message(
    language: str,
    mode: str,
    *,
    interests: list[str] | None = None,
    style_label: str | None = None,
    duration: int = DEFAULT_ROUTE_MINUTES,
) -> str:
    """Build one complete request for the existing controlled route entry."""
    if mode == "classic":
        return f"{language}，经典模式，{duration}分钟"
    if mode != "custom":
        raise ValueError(f"未知游览模式：{mode}")
    selected_interests = list(interests or [])
    if not selected_interests or style_label not in STYLES:
        raise ValueError("定制模式必须选择工艺偏好和讲解风格。")
    interest_text = "、".join(selected_interests)
    return (
        f"{language}，定制模式，{duration}分钟，"
        f"我喜欢{interest_text}，选择{style_label}风格"
    )


_CHAT_ROUTE_ACTION_RE = re.compile(
    r"\b(?:create|build|make|plan|generate|start)\b[^.?!]{0,60}"
    r"\b(?:route|tour|itinerary)\b",
    re.IGNORECASE,
)
_CHAT_ROUTE_ACTION_TERMS = (
    "路线", "规划", "怎么逛", "游览", "参观顺序", "导览", "带我逛",
    "创建路线", "新建路线", "生成路线", "安排路线",
)
_CHAT_LANGUAGE_ALIASES = {
    "中文": "中文", "普通话": "中文", "汉语": "中文", "chinese": "中文", "mandarin": "中文",
    "英语": "英语", "英文": "英语", "english": "英语",
    "粤语": "粤语", "cantonese": "粤语",
    "韩语": "韩语", "korean": "韩语", "日语": "日语", "japanese": "日语",
}
_CHAT_STYLE_ALIASES = {
    "child-friendly": "儿童友好", "child friendly": "儿童友好",
    "neutral": "中性清晰", "professional": "专业讲解",
    "family": "亲子共游", "student research": "研学观察",
    "listen only": "静听模式", "exploration game": "探秘闯关",
}
_CHAT_INTEREST_ALIASES = {
    "grey plaster": "灰塑", "gray plaster": "灰塑", "plasterwork": "灰塑",
    "wood carving": "木雕", "stone carving": "石雕", "brick carving": "砖雕",
    "ceramic sculpture": "陶塑", "architectural decoration": "建筑装饰",
}


def _chat_route_request_message(message: str) -> str:
    """Adapt a chat route command into the existing C1/C2 text contract.

    This is deliberately an input adapter, not a planner: the returned text
    still goes through ``route_initial_request``, profile collection, duration
    parsing, style-conflict validation, ``direct_route`` and its route audit.
    A fully stated request uses the exact same canonical shape as the sidebar;
    incomplete or conflicting requests retain their original words so C2 can
    ask its existing clarification questions without guessing missing fields.
    """
    original = message.strip()
    lowered = original.casefold()
    is_route_action = (
        any(term in original for term in _CHAT_ROUTE_ACTION_TERMS)
        or bool(_CHAT_ROUTE_ACTION_RE.search(original))
    )
    if not is_route_action:
        return message

    mode: str | None = None
    if "定制" in original or re.search(r"\b(?:custom|customized|tailored?)\b", lowered):
        mode = "custom"
    elif "经典" in original or re.search(r"\bclassic\b", lowered):
        mode = "classic"

    languages = {
        value for alias, value in _CHAT_LANGUAGE_ALIASES.items() if alias.casefold() in lowered
    }
    language = next(iter(languages)) if len(languages) == 1 else None
    duration = parse_duration_minutes(original)
    interests = [
        craft for craft in CRAFT_INTERESTS
        if craft in original or any(alias in lowered for alias, mapped in _CHAT_INTEREST_ALIASES.items() if mapped == craft)
    ]
    styles = [label for label in STYLES if label in original]
    styles.extend(
        label for alias, label in _CHAT_STYLE_ALIASES.items() if alias in lowered and label not in styles
    )

    # Matching this exact form is what makes the chat and sidebar entrances
    # equivalent.  ``parse_duration_minutes`` is intentionally run again by
    # C2 after this conversion; no parsed value is written directly to state.
    if (
        language is not None
        and duration.ok
        and duration.minutes is not None
        and mode == "classic"
    ):
        return _route_request_message(language, mode, duration=duration.minutes)
    if (
        language is not None
        and duration.ok
        and duration.minutes is not None
        and mode == "custom"
        and interests
        and len(styles) == 1
    ):
        return _route_request_message(
            language, mode, interests=interests, style_label=styles[0], duration=duration.minutes,
        )

    # English route/action words otherwise need a Chinese route marker for the
    # existing deterministic router.  Add only values explicitly recognized
    # above and preserve the source utterance, so C2 remains authoritative for
    # missing fields and incompatible style choices.
    hints = ["帮我规划路线"]
    if language:
        hints.append(language)
    if mode == "classic":
        hints.append("经典模式")
    elif mode == "custom":
        hints.append("定制模式")
    if interests:
        hints.append("我喜欢" + "、".join(interests))
    if styles:
        hints.append("和".join(f"选择{style}风格" for style in styles))
    hints.append(original)
    return "，".join(hints)


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
        reply = adapter.send(_chat_route_request_message(message))
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


def _progress_panel_markup(itinerary) -> str:
    """Return only visitor-safe progress HTML; no Agent text becomes markup."""
    if not itinerary.stops:
        return (
            "<div class='progress-panel empty'><b>导览进度</b>"
            "<span>尚未开始导览，生成路线后将在这里显示点位进度。</span></div>"
        )
    steps = "".join(
        "<div class='progress-step {status}'><div class='progress-dot'>{symbol}</div>"
        "<span>{name}</span></div>".format(
            status=escape(stop.status),
            symbol="✓" if stop.status == "completed" else "●" if stop.status == "current" else "○",
            name=escape(stop.name),
        )
        for stop in itinerary.stops
    )
    return (
        "<div class='progress-panel'><div class='progress-header'><b>导览进度</b>"
        "<span>已完成 {completed}/{total} · 当前：{current}</span></div>"
        "<div class='progress-track'>{steps}</div></div>".format(
            completed=itinerary.completed_count,
            total=itinerary.total_count,
            current=escape(itinerary.current_stop),
            steps=steps,
        ),
    )


def _render_chat_message(item: dict[str, object]) -> None:
    """Render a visitor-safe WeChat-style message bubble without raw model HTML."""
    role = str(item.get("role") or "assistant")
    is_visitor = role == "user"
    content = escape(str(item.get("content") or "")).replace("\n", "<br>")
    # Public answers allow exactly one reviewed external destination.  It is
    # escaped before this replacement, and the URL constant is not model
    # supplied, so the custom chat HTML can offer a clickable official entry
    # without opening arbitrary links from assistant text.
    official_url = escape(OFFICIAL_TICKETING_URL)
    content = content.replace(
        official_url,
        f'<a href="{official_url}" target="_blank" rel="noopener noreferrer">{official_url}</a>',
    )
    scene_kind = str(item.get("scene_kind") or "")
    scene_label = SCENE_LABELS.get(scene_kind, "") if not is_visitor else ""
    service_text = str(item.get("service_text") or "")
    avatar = "游" if is_visitor else "祠"
    speaker = "游客" if is_visitor else "小祠导游"
    bubble = (
        f"<div class='wechat-bubble'><div class='wechat-speaker'>{escape(speaker)}"
        f"{f' · {escape(scene_label)}' if scene_label else ''}</div>{content}"
        f"{f'<div class=\"wechat-service\">下一步：{escape(service_text)}</div>' if service_text else ''}"
        "</div>"
    )
    row_class = "visitor" if is_visitor else "assistant"
    st.markdown(
        f"<div class='wechat-row {row_class}'>{bubble}<div class='wechat-avatar'>{avatar}</div></div>"
        if is_visitor
        else f"<div class='wechat-row {row_class}'><div class='wechat-avatar'>{avatar}</div>{bubble}</div>",
        unsafe_allow_html=True,
    )


@st.fragment
def _render_route_sidebar(adapter: DemoAdapter) -> None:
    """Keep preference-only changes local so mode switching does not redraw chat."""
    with st.sidebar:
        st.subheader("路线快捷创建")
        mode_label = st.radio("游览模式", list(JOURNEY_MODES), horizontal=True, key="tour_mode_selection")
        selected_mode = JOURNEY_MODES[mode_label]
        duration_choice = st.selectbox(
            "游览时长", ["30分钟", "60分钟", "90分钟", "自定义"],
            index=1, key="duration_selection",
            help="选择常用时长；如需其他时间，请选择“自定义”。",
        )
        if duration_choice == "自定义":
            st.caption("请输入 20–120 分钟的整数。")
            duration = st.number_input(
                "自定义时长（分钟）", min_value=MIN_ROUTE_MINUTES,
                max_value=MAX_ROUTE_MINUTES, value=DEFAULT_ROUTE_MINUTES, step=5,
                key="custom_duration", label_visibility="visible",
            )
        else:
            duration = int(duration_choice.removesuffix("分钟"))
        interests: list[str] = []
        style_label: str | None = None
        if selected_mode == "custom":
            interests = st.multiselect(
                "喜欢的工艺类型", CRAFT_INTERESTS, default=["灰塑"],
                placeholder="请选择至少一种工艺", key="craft_interest_selection",
            )
            style_label = st.selectbox("讲解风格", list(STYLES), key="guide_style_selection")
        can_plan = selected_mode == "classic" or bool(interests)
        if st.button("开始规划路线", type="primary", use_container_width=True, disabled=not can_plan, key="plan_route"):
            request = _route_request_message(
                "中文", selected_mode, interests=interests,
                style_label=style_label, duration=int(duration),
            )
            _send(adapter, request)
            st.rerun()
        if st.button("重置会话", use_container_width=True, key="reset_conversation"):
            adapter.reset()
            st.session_state.messages = []
            st.session_state.itinerary = adapter.itinerary
            _start_session(adapter)
            st.rerun()


def _render_progress_dock(itinerary) -> None:
    """Use a native disclosure control so fixed progress always responds."""
    st.markdown(
        "<details class='progress-dock' open><summary aria-label='隐藏或展开导览进度'></summary>"
        f"{_progress_panel_markup(itinerary)}</details><div class='progress-spacer'></div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="祠语智游", page_icon="🏛️", layout="wide",
        initial_sidebar_state="expanded",
    )
    _configure_environment()
    st.markdown("""<style>
    .stApp {background:linear-gradient(140deg,#f7f1e6 0%,#efe2cc 100%);color:#27201b;}
    header[data-testid='stHeader'],[data-testid='stToolbar'] {background:transparent !important;pointer-events:none;}
    header[data-testid='stHeader'] [data-testid='stExpandSidebarButton'] {pointer-events:auto;}
    .block-container {max-width:1080px;padding-top:.45rem;padding-bottom:4.5rem;}
    [data-testid='stBottom'],.stBottom {background:rgba(247,241,230,.98) !important;padding-top:.2rem !important;padding-bottom:.05rem !important;min-height:0 !important;}
    [data-testid='stBottom'] > div,[data-testid='stBottom'] > div > div {padding-top:.15rem !important;padding-bottom:.05rem !important;margin-bottom:0 !important;min-height:0 !important;}
    [data-testid='stSidebar'] {background:#39251f;}
    [data-testid='stSidebar'] h1,[data-testid='stSidebar'] h2,[data-testid='stSidebar'] h3,[data-testid='stSidebar'] label,[data-testid='stSidebar'] [data-testid='stWidgetLabel'] p,[data-testid='stSidebar'] [role='radiogroup'] p {color:#fff8ec !important;}
    [data-testid='stSidebar'] [data-testid='stCaptionContainer'] p {color:#d8c7b4 !important;opacity:1 !important;}
    [data-testid='stSidebar'] button[kind='secondary'],[data-testid='stSidebar'] button[kind='secondary'] * {color:#3b291f !important;background:#fffdf9;}
    [data-testid='stSidebar'] button[kind='primary'],[data-testid='stSidebar'] button[kind='primary'] * {color:#fff !important;}
    [data-testid='stSidebar'] [data-testid='stNumberInput'] {max-width:14rem;}
    [data-testid='stSidebar'] [data-testid='stSidebarCollapseButton'],[data-testid='stSidebar'] button[kind='header'] {background:#c99745 !important;border:1px solid #f4d98f !important;border-radius:.6rem !important;opacity:1 !important;}
    [data-testid='stSidebar'] [data-testid='stSidebarCollapseButton'] svg,[data-testid='stSidebar'] button[kind='header'] svg {fill:#fffdf8 !important;color:#fffdf8 !important;stroke:#fffdf8 !important;}
    [data-testid='stSidebarCollapseButton'] button,[data-testid='stExpandSidebarButton'],[data-testid='stSidebarCollapsedControl'],button[kind='headerNoPadding'][data-testid='stBaseButton-headerNoPadding'] {background:#c99745 !important;border:1px solid #f4d98f !important;border-radius:.6rem !important;opacity:1 !important;}
    [data-testid='stSidebarCollapseButton'] button svg,[data-testid='stExpandSidebarButton'] svg,[data-testid='stSidebarCollapsedControl'] svg,button[kind='headerNoPadding'][data-testid='stBaseButton-headerNoPadding'] svg {fill:#fffdf8 !important;color:#fffdf8 !important;stroke:#fffdf8 !important;}
    .hero {padding:1.15rem 1.4rem;border-radius:18px;background:linear-gradient(110deg,#52271e,#7b3c2e);color:#fff8ec;margin:.8rem 0;box-shadow:0 10px 24px rgba(62,32,21,.18);}
    .hero h1 {font-size:1.65rem;margin:0 0 .25rem;}.hero p {margin:0;color:#f8e8ce;}
    .progress-panel {position:fixed;top:.45rem;left:max(1rem,calc(50vw - 450px));right:max(1rem,calc(50vw - 450px));z-index:50;padding:.85rem 1rem 1rem;border:1px solid #d4b978;border-radius:14px;background:rgba(255,251,242,.98);margin:0;overflow:hidden;box-shadow:0 4px 12px rgba(76,48,27,.14);}
    .progress-spacer {height:11.5rem;}
    .progress-dock summary {position:fixed;top:.8rem;right:1.3rem;z-index:60;display:block;list-style:none;min-height:2rem;padding:.35rem .65rem;background:#6f2d26;color:#fff8ec;border:1px solid #d4b978;border-radius:.55rem;font-size:.8rem;font-weight:600;box-shadow:0 2px 7px rgba(76,48,27,.18);cursor:pointer;}.progress-dock summary::-webkit-details-marker {display:none;}.progress-dock summary::after {content:'隐藏导览进度';}.progress-dock:not([open]) summary::after {content:'展开导览进度';}.progress-dock:not([open]) .progress-panel {display:none;}.progress-dock:not([open]) + .progress-spacer {height:0;}
    .stApp:has([data-testid='stSidebar'][aria-expanded='true']) .progress-panel {left:max(calc(21rem + 1rem),calc(50vw + 10.5rem - 450px));right:max(1rem,calc(50vw - 10.5rem - 450px));}
    .stApp:has([data-testid='stSidebar'][aria-expanded='true']) .progress-dock summary {right:max(1.3rem,calc(50vw - 10.5rem - 450px + .5rem));}
    .progress-panel.empty {display:flex;gap:.7rem;align-items:center;color:#6c5d4d;}.progress-panel.empty span {font-size:.9rem;}
    .progress-header {display:flex;justify-content:space-between;gap:1rem;margin-bottom:.75rem;color:#5e3527;font-size:.9rem;}.progress-header span {color:#776553;}
    .progress-track {display:flex;gap:.25rem;min-width:max-content;padding:0 .1rem .15rem;}.progress-step {width:112px;position:relative;text-align:center;color:#937f6d;font-size:.76rem;line-height:1.25;}.progress-step:not(:last-child):after {content:'';position:absolute;top:.45rem;left:58%;width:85%;height:2px;background:#d9c8b5;z-index:0;}.progress-dot {position:relative;z-index:1;width:1.15rem;height:1.15rem;margin:0 auto .35rem;border-radius:50%;background:#fffaf0;display:grid;place-items:center;font-size:.68rem;border:2px solid #bca48b;color:#bca48b;}.progress-step.completed,.progress-step.current {color:#633326;}.progress-step.completed .progress-dot {background:#9a6b36;border-color:#9a6b36;color:#fff;}.progress-step.current .progress-dot {background:#6f2d26;border-color:#6f2d26;color:#fff;box-shadow:0 0 0 4px rgba(111,45,38,.13);}.progress-step.completed:not(:last-child):after {background:#9a6b36;}
    .wechat-row {display:flex;align-items:flex-start;gap:.55rem;margin:.85rem 0;}.wechat-row.visitor {justify-content:flex-end;}.wechat-avatar {flex:0 0 2.45rem;height:2.45rem;border-radius:.7rem;display:grid;place-items:center;font-weight:700;color:#fff;background:#a46c32;box-shadow:0 2px 7px rgba(74,44,21,.16);}.wechat-row.visitor .wechat-avatar {background:#e9715f;}.wechat-bubble {max-width:min(78%,780px);padding:.7rem .9rem;border-radius:4px 15px 15px 15px;background:#fffdf8;border:1px solid #dfd1bd;box-shadow:0 2px 6px rgba(76,48,27,.06);line-height:1.7;color:#2e2a27;}.wechat-row.visitor .wechat-bubble {border-radius:15px 4px 15px 15px;background:#e7f5d9;border-color:#cbe3b8;}.wechat-speaker {font-size:.78rem;color:#8a7665;margin-bottom:.25rem;}.wechat-service {margin-top:.55rem;padding-top:.45rem;border-top:1px solid #e6dac9;color:#785844;font-size:.86rem;}.wechat-row.visitor .wechat-service {border-color:#cbe3b8;}
    @media (max-width: 700px) {.block-container {padding:.35rem .75rem 6.5rem;}.progress-panel {left:.75rem;right:.75rem;top:.35rem;}.progress-spacer {height:12.5rem;}.progress-track {overflow-x:auto;}.progress-header {display:block;}.progress-header span {display:block;margin-top:.25rem;}.progress-panel.empty {align-items:flex-start;flex-direction:column;gap:.25rem;}.progress-dock summary {right:.8rem;top:.55rem;}}
    </style>""", unsafe_allow_html=True)
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
    itinerary = st.session_state.itinerary
    _render_progress_dock(itinerary)
    st.markdown("<div class='hero'><h1>祠语智游</h1><p>陈家祠智能导览｜跟随对话，探索岭南建筑与工艺之美。</p></div>", unsafe_allow_html=True)

    _render_route_sidebar(adapter)

    st.markdown("#### 与导游对话")
    for item in st.session_state.messages:
        _render_chat_message(item)
    st.caption("您可以直接提问，或使用快捷指令推进导览。")
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
