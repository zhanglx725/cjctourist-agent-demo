"""Competition-facing Streamlit shell using public messages from one Agent turn."""

from __future__ import annotations

import os
import sys
import logging
import re
import base64
import threading
from datetime import date
from html import escape
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
BACKGROUND_IMAGE = Path(__file__).resolve().parent / "assets" / "chen-clan-heritage-tech-bg-v2.png"
PHOTO_POSE_GRID_DIR = Path(__file__).resolve().parent / "assets" / "photo_pose_grids"
MAP_IMAGE = ROOT / "outputs" / "visitor_point_map_v1.png"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.demo_adapter import DemoAdapter
from controlled_knowledge_query import OFFICIAL_TICKETING_URL
from duration_parser import parse_duration_minutes
from photo_hint_card import build_photo_hint_card


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
QUICK_ACTIONS = ["拍照提示", "我到了", "再讲详细一点", "完成本点"]
SCENE_LABELS = {
    "route_planning": "路线规划",
    "welcome": "欢迎来到陈家祠",
    "route_opening": "导览开场",
    "stop_guidance": "当前点讲解",
    "detail_expansion": "延伸讲解",
    "tour_qa": "导览问答",
    "tour_closing": "游览总结",
    "assistant": "导览回复",
}

PHOTO_POSE_GRID_RULES = (
    (("月台", "moon_platform"), "pose-grid-moon-platform.png"),
    (("后东", "rear_east"), "pose-grid-rear-east.png"),
    (("后西", "rear_west"), "pose-grid-rear-west.png"),
    (("后庭", "rear_courtyard"), "pose-grid-rear-center.png"),
    (("前东", "front_east", "courtyard_east"), "pose-grid-front-east.png"),
    (("前西", "front_west", "courtyard_west"), "pose-grid-front-center.png"),
    (("前院", "front_courtyard"), "pose-grid-front-center.png"),
)


def _photo_pose_grid(current_stop: str) -> Path:
    """Return one complete nine-pose grid for the current formal stop."""
    normalized = str(current_stop or "").strip().lower()
    for aliases, filename in PHOTO_POSE_GRID_RULES:
        if any(alias.lower() in normalized for alias in aliases):
            return PHOTO_POSE_GRID_DIR / filename
    return PHOTO_POSE_GRID_DIR / "pose-grid-front-center.png"


@st.cache_data
def _background_image_data() -> str:
    """Return the bundled background as a deployment-safe data URI payload."""
    return base64.b64encode(BACKGROUND_IMAGE.read_bytes()).decode("ascii")


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


@st.cache_resource(show_spinner=False)
def _begin_rag_warmup() -> threading.Thread | None:
    """Warm local retrieval models while the visitor is choosing a route."""
    if _secret("DEMO_RAG_WARMUP", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return None

    def warm() -> None:
        try:
            from agent_graph import warm_rag_models
            warm_rag_models()
        except Exception as exc:
            # Warm-up is only a latency optimization. Normal RAG error handling
            # remains authoritative if the local dependency is unavailable.
            LOGGER.warning("rag_background_warmup_failed=%s", type(exc).__name__)

    worker = threading.Thread(target=warm, name="cjc-rag-warmup", daemon=True)
    worker.start()
    return worker


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


def _sidebar_plan_request(
    *,
    active_tour: bool,
    mode: str,
    interests: list[str] | None,
    style_label: str | None,
    duration: int,
) -> str:
    """Build an initial route or a current-position remaining-time replan."""
    if active_tour:
        return f"我还有 {duration} 分钟"
    return _route_request_message(
        "中文", mode, interests=interests,
        style_label=style_label, duration=duration,
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
    # Streamlit suppresses INFO logging by default.  Keep an explicit,
    # secret-free terminal trace for the active-tour duration control so a
    # real replan can always be timed even if a backend branch rejects it.
    active_duration_replan = (
        adapter.itinerary.total_count > 0
        and not getattr(adapter.itinerary, "is_finished", False)
        and ("分钟" in message or "重规划" in message or "重新规划" in message)
    )
    if active_duration_replan:
        print(
            "REPLAN_UI_START "
            f"completed_stops={adapter.itinerary.completed_count} "
            f"total_stops={adapter.itinerary.total_count}",
            flush=True,
        )
    first_arrival = (
        message.strip(" ，。！？!?\t\r\n") in {"我到了", "到了"}
        and adapter.itinerary.total_count > 0
        and adapter.itinerary.completed_count == 0
    )
    spinner_text = (
        "首次到达：正在准备专属开场与点位讲解…"
        if first_arrival else "正在组织本次导览…"
    )
    with st.spinner(spinner_text):
        reply = adapter.send(_chat_route_request_message(message))
    if active_duration_replan:
        print(
            "REPLAN_UI_END "
            f"wall_seconds={reply.elapsed_seconds:.3f} error={reply.is_error}",
            flush=True,
        )
    LOGGER.info(
        "demo_turn_completed elapsed_seconds=%.3f first_arrival=%s error=%s",
        reply.elapsed_seconds, first_arrival, reply.is_error,
    )
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
            "<div class='progress-panel route-progress-panel empty'><b>导览进度</b>"
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
        "<div class='progress-panel route-progress-panel'><div class='progress-header'><b>导览进度</b>"
        "<span>已完成 {completed}/{total} · 当前：{current}</span></div>"
        "<div class='progress-track'>{steps}</div></div>".format(
            completed=itinerary.completed_count,
            total=itinerary.total_count,
            current=escape(itinerary.current_stop),
            steps=steps,
        )
    )


def _craft_progress_markup(messages: list[dict[str, object]]) -> str:
    """Render achievements derived only from visitor-visible guide content."""
    craft_names = ("木雕", "石雕", "砖雕", "灰塑", "陶塑", "彩绘")
    unlocked = set(_unlocked_crafts(messages))
    items = "".join(
        "<div class='craft-badge {status}'><span class='craft-symbol'>{symbol}</span>"
        "<span>{name}</span></div>".format(
            status="unlocked" if craft in unlocked else "locked",
            symbol="✓" if craft in unlocked else "◇",
            name=escape(craft),
        )
        for craft in craft_names
    )
    return (
        "<div class='progress-panel craft-progress-panel'>"
        "<div class='progress-header'><b>工艺解锁进度</b>"
        f"<span>已解锁 {len(unlocked)}/{len(craft_names)}</span></div>"
        f"<div class='craft-grid'>{items}</div></div>"
    )


def _unlocked_crafts(messages: list[dict[str, object]]) -> tuple[str, ...]:
    """Return crafts actually named in visitor-visible guidance or QA."""
    craft_names = ("木雕", "石雕", "砖雕", "灰塑", "陶塑", "彩绘")
    eligible_text = "\n".join(
        str(item.get("content") or "")
        for item in messages
        if item.get("role") == "assistant"
        and item.get("scene_kind") in {"stop_guidance", "tour_qa", "qa_follow_up_detail"}
    )
    return tuple(craft for craft in craft_names if craft in eligible_text)


def _is_genuine_visitor_question(item: dict[str, object]) -> bool:
    """Exclude route setup and button-like controls from interaction totals."""
    if item.get("role") != "user":
        return False
    text = str(item.get("content") or "").strip(" ，。！？!?\t\r\n")
    if not text:
        return False
    if text in {
        *QUICK_ACTIONS,
        "到了", "结束游览", "结束导览", "结束路线",
        "查看游览地图", "生成纪念卡", "查看纪念卡", "附近美食推荐",
    }:
        return False
    return not bool(re.search(r"(?:经典模式|定制模式).{0,40}\d+分钟", text))


def _tour_summary_card_markup(itinerary, messages: list[dict[str, object]]) -> str:
    """Build one visitor-safe completion card from public presentation data."""
    closing_text = "\n".join(
        str(item.get("content") or "")
        for item in messages
        if item.get("role") == "assistant" and item.get("scene_kind") == "tour_closing"
    )
    title_match = re.search(r"称号(?:是|为)[“\"]([^”\"]+)[”\"]", closing_text)
    title = title_match.group(1) if title_match else "一日看尽岭南花"
    unlocked = _unlocked_crafts(messages)
    highlight_candidates = (
        "独角狮", "金蟾吐瑞气", "公孙玩乐", "苏武牧羊", "宝相花",
        "赤壁之战", "风尘三侠", "郭子仪祝寿", "麒麟", "鳌鱼",
    )
    highlights = tuple(name for name in highlight_candidates if name in closing_text)[:6]
    question_count = sum(_is_genuine_visitor_question(item) for item in messages)
    route = "".join(
        f"<span class='summary-route-stop'>✓ {escape(stop.name)}</span>"
        for stop in itinerary.stops
    )
    craft_badges = "".join(
        f"<span class='summary-badge unlocked'>✓ {escape(craft)}</span>"
        for craft in unlocked
    ) or "<span class='summary-empty'>本次尚未解锁工艺徽章</span>"
    highlight_badges = "".join(
        f"<span class='summary-badge'>{escape(name)}</span>" for name in highlights
    ) or "<span class='summary-empty'>继续提问，可以补充本次游览看点</span>"
    return (
        "<section class='tour-summary-card'>"
        "<div class='summary-seal'>完成</div>"
        "<div class='summary-kicker'>本次导览圆满完成</div>"
        f"<h2>{escape(title)}</h2>"
        f"<div class='summary-date'>{date.today().isoformat()}</div>"
        "<div class='summary-disclaimer'>趣味纪念称号，不代表官方认证或游客评级</div>"
        "<div class='summary-stats'>"
        f"<div><strong>{itinerary.completed_count}</strong><span>参观讲解点</span></div>"
        f"<div><strong>{len(unlocked)}/6</strong><span>解锁工艺</span></div>"
        f"<div><strong>{len(highlights)}</strong><span>今日看点</span></div>"
        f"<div><strong>{question_count}</strong><span>提问互动</span></div>"
        "</div>"
        f"<div class='summary-section'><b>路线回顾</b><div class='summary-route'>{route}</div></div>"
        f"<div class='summary-section'><b>工艺成就</b><div class='summary-badges'>{craft_badges}</div></div>"
        f"<div class='summary-section'><b>今日看点</b><div class='summary-badges'>{highlight_badges}</div></div>"
        "<div class='summary-wish'>愿你今日看到的岭南繁花，归去之后仍可慢慢回味。</div>"
        "</section>"
    )


def _tour_end_record_markup(itinerary, *, finished_early: bool) -> str:
    """Build the compact on-page record shown for every finished tour."""
    visited = tuple(stop.name for stop in itinerary.stops if stop.status == "completed")
    route_text = " · ".join(visited) if visited else "尚未确认完成点位"
    heading = "本次导览已提前结束" if finished_early else "本次导览圆满完成"
    return (
        "<section class='tour-end-record'>"
        f"<div><b>{heading}</b><span>已参观 {itinerary.completed_count} 个讲解点</span></div>"
        f"<p>路线记录：{escape(route_text)}</p>"
        "</section>"
    )


def _tour_souvenir_svg(itinerary, messages: list[dict[str, object]]) -> bytes:
    """Create a self-contained 16:9 downloadable souvenir image."""
    closing_text = "\n".join(
        str(item.get("content") or "")
        for item in messages
        if item.get("role") == "assistant" and item.get("scene_kind") == "tour_closing"
    )
    title_match = re.search(r"称号(?:是|为)[“\"]([^”\"]+)[”\"]", closing_text)
    title = title_match.group(1) if title_match else "一日看尽岭南花"
    unlocked = _unlocked_crafts(messages)
    highlight_candidates = (
        "独角狮", "金蟾吐瑞气", "公孙玩乐", "苏武牧羊", "宝相花",
        "赤壁之战", "风尘三侠", "郭子仪祝寿", "麒麟", "鳌鱼",
    )
    highlights = tuple(name for name in highlight_candidates if name in closing_text)[:6]
    route_text = "  ·  ".join(stop.name for stop in itinerary.stops)
    craft_text = "  ·  ".join(unlocked) if unlocked else "尚未解锁工艺徽章"
    highlight_text = "  ·  ".join(highlights) if highlights else "本次看点等待补充"
    background = _background_image_data()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
<defs><linearGradient id="shade" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#451d18" stop-opacity=".9"/><stop offset="1" stop-color="#073f42" stop-opacity=".9"/></linearGradient></defs>
<image width="1600" height="900" href="data:image/png;base64,{background}" preserveAspectRatio="xMidYMid slice"/>
<rect width="1600" height="900" fill="url(#shade)"/>
<rect x="48" y="48" width="1504" height="804" rx="34" fill="none" stroke="#e5bd68" stroke-width="4"/>
<rect x="66" y="66" width="1468" height="768" rx="26" fill="none" stroke="#e5bd68" stroke-opacity=".35" stroke-width="2"/>
<text x="800" y="145" text-anchor="middle" fill="#e9c878" font-size="28" letter-spacing="8">祠语智游 · 游览纪念</text>
<text x="800" y="235" text-anchor="middle" fill="#fff4d3" font-size="62" font-family="KaiTi,STKaiti,serif">{escape(title)}</text>
<text x="800" y="278" text-anchor="middle" fill="#bcd3d0" font-size="22">{date.today().isoformat()} · 趣味纪念称号</text>
<g font-family="Microsoft YaHei,sans-serif" text-anchor="middle"><rect x="250" y="330" width="1100" height="120" rx="20" fill="#061f23" fill-opacity=".62" stroke="#dcb25e" stroke-opacity=".45"/>
<text x="470" y="380" fill="#f0c66f" font-size="44">{itinerary.completed_count}</text><text x="470" y="420" fill="#d7e2de" font-size="22">参观讲解点</text>
<text x="800" y="380" fill="#f0c66f" font-size="44">{len(unlocked)}/6</text><text x="800" y="420" fill="#d7e2de" font-size="22">解锁工艺</text>
<text x="1130" y="380" fill="#f0c66f" font-size="44">{len(highlights)}</text><text x="1130" y="420" fill="#d7e2de" font-size="22">今日看点</text></g>
<g font-family="Microsoft YaHei,sans-serif"><text x="180" y="520" fill="#efca7f" font-size="25">路线回顾</text><text x="180" y="565" fill="#eef6f1" font-size="25">{escape(route_text)}</text>
<text x="180" y="640" fill="#efca7f" font-size="25">工艺成就</text><text x="180" y="685" fill="#eef6f1" font-size="25">{escape(craft_text)}</text>
<text x="180" y="760" fill="#efca7f" font-size="25">今日看点</text><text x="180" y="805" fill="#eef6f1" font-size="25">{escape(highlight_text)}</text></g>
<text x="800" y="842" text-anchor="middle" fill="#ead9b3" font-size="21" font-family="KaiTi,STKaiti,serif">愿你今日看到的岭南繁花，归去之后仍可慢慢回味。</text>
<circle cx="1415" cy="165" r="58" fill="none" stroke="#e5bd68" stroke-width="4"/><text x="1415" y="178" text-anchor="middle" fill="#efc875" font-size="30" font-family="KaiTi,serif">完成</text>
</svg>"""
    return svg.encode("utf-8")


def _render_chat_message(item: dict[str, object]) -> None:
    """Render a visitor-safe WeChat-style message bubble without raw model HTML."""
    role = str(item.get("role") or "assistant")
    is_visitor = role == "user"
    scene_kind = str(item.get("scene_kind") or "")
    raw_content = str(item.get("content") or "").strip()
    if is_visitor:
        content = escape(raw_content).replace("\n", "<br>")
    else:
        blocks = [
            block.strip()
            for block in re.split(r"\n\s*\n+", raw_content)
            if block.strip()
        ]
        if scene_kind == "detail_expansion":
            intro = blocks[0] if blocks else ""
            cards = []
            for block in blocks[1:]:
                lines = [line.strip() for line in block.splitlines() if line.strip()]
                if not lines:
                    continue
                title, body = lines[0], " ".join(lines[1:])
                cards.append(
                    "<section class='detail-expansion-card'>"
                    f"<b>{escape(title)}</b>"
                    f"<p>{escape(body)}</p>"
                    "</section>"
                )
            content = (
                f"<span class='detail-expansion-intro'>{escape(intro)}</span>"
                f"<div class='detail-expansion-grid'>{''.join(cards)}</div>"
            )
        else:
            # Stop narration often arrives as one sentence per line. Present it
            # like a human guide instead of making each sentence a new paragraph.
            if scene_kind in {"stop_guidance", "qa_follow_up_detail"}:
                lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
                blocks = []
                current: list[str] = []
                current_length = 0
                for line in lines:
                    if current and (len(current) >= 4 or current_length + len(line) > 240):
                        blocks.append("".join(current))
                        current = []
                        current_length = 0
                    current.append(line)
                    current_length += len(line)
                if current:
                    blocks.append("".join(current))
            content = "".join(
                f"<span class='chat-paragraph'>{escape(block).replace(chr(10), '<br>')}</span>"
                for block in blocks
            )
    # Public answers allow exactly one reviewed external destination.  It is
    # escaped before this replacement, and the URL constant is not model
    # supplied, so the custom chat HTML can offer a clickable official entry
    # without opening arbitrary links from assistant text.
    official_url = escape(OFFICIAL_TICKETING_URL)
    content = content.replace(
        official_url,
        f'<a href="{official_url}" target="_blank" rel="noopener noreferrer">{official_url}</a>',
    )
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


@st.dialog("陈家祠导览地图", width="large")
def _show_tour_map() -> None:
    """Show the simplified visitor point map without changing tour state."""
    st.image(MAP_IMAGE, use_container_width=True)
    st.caption("简图用于辅助辨认主要点位；现场通行与开放情况请以馆方指引为准。")


@st.dialog("拍照提示", width="large")
def _show_photo_hint_card(text: str, current_stop: str = "") -> None:
    """Show optional pose guidance outside the main narration flow."""
    card = build_photo_hint_card(text)
    st.markdown("<div class='photo-hint-card-marker'></div>", unsafe_allow_html=True)
    with st.container(key="photo_guide_card"):
        st.markdown(
            "<div class='photo-card-heading'>"
            "<span>祠语智游 · 拍照锦囊</span>"
            f"<h3>{escape(card.title)}</h3>"
            "<small>九宫格姿势参考 · 请结合现场空间自然调整</small>"
            "</div>",
            unsafe_allow_html=True,
        )
        pose_column, advice_column = st.columns([1, 1], gap="large", vertical_alignment="center")
        with pose_column:
            with st.container(key="photo_pose_panel"):
                st.image(_photo_pose_grid(current_stop), use_container_width=True)
        with advice_column:
            with st.container(key="photo_advice_panel"):
                st.markdown(
                    "<div class='photo-advice-grid'>"
                    f"<section><b>人物站位与姿势</b><p>{escape(card.pose)}</p></section>"
                    f"<section><b>构图方式</b><p>{escape(card.composition)}</p></section>"
                    f"<section><b>客流与光线</b><p>{escape(card.conditions)}</p></section>"
                    f"<section><b>安全提醒</b><p>{escape(card.safety)}</p></section>"
                    "</div>",
                    unsafe_allow_html=True,
                )
    if st.button("关闭", use_container_width=True, key="close_photo_hint"):
        st.rerun()


@st.dialog("游览纪念卡", width="medium")
def _show_souvenir_card(itinerary, messages: list[dict[str, object]]) -> None:
    """Preview and download the generated souvenir without mutating tour state."""
    st.markdown(
        _tour_summary_card_markup(itinerary, messages),
        unsafe_allow_html=True,
    )
    if st.session_state.get("souvenir_show_map", False):
        st.image(MAP_IMAGE, use_container_width=True)
        st.caption("本次游览点位简图 · 现场通行与开放情况请以馆方指引为准。")
    actions = st.columns(3)
    actions[0].download_button(
        "下载纪念卡",
        data=_tour_souvenir_svg(itinerary, messages),
        file_name=f"祠语智游_游览纪念卡_{date.today().isoformat()}.svg",
        mime="image/svg+xml",
        use_container_width=True,
        key="download_souvenir_card",
    )
    if actions[1].button("查看游览地图", use_container_width=True, key="souvenir_map"):
        st.session_state.souvenir_show_map = not st.session_state.get("souvenir_show_map", False)
        st.rerun(scope="fragment")
    if actions[2].button("关闭", use_container_width=True, key="close_souvenir"):
        st.session_state.souvenir_show_map = False
        st.rerun()


@st.fragment
def _render_route_sidebar(adapter: DemoAdapter) -> None:
    """Keep preference-only changes local so mode switching does not redraw chat."""
    itinerary = adapter.itinerary
    active_tour = bool(
        itinerary.total_count
        and not getattr(itinerary, "is_finished", False)
    )
    with st.sidebar:
        st.markdown(
            "<div class='sidebar-brand'>"
            "<h1>祠语智游：雕檐阅岁月，AI叙风华</h1>"
            "<p>多样导游人设·沉浸式讲解·解锁参观成就</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        title_column, map_column = st.columns([1.9, 1.1], vertical_alignment="center")
        with title_column:
            st.subheader("路线快捷创建")
        with map_column:
            if st.button("查看地图", key="show_tour_map", use_container_width=True):
                _show_tour_map()
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
        if active_tour:
            st.caption("中途重规划会保留当前模式与偏好；这里选择的是从当前点位起算的剩余时间。")
        interests: list[str] = []
        style_label: str | None = None
        if selected_mode == "custom":
            interests = st.multiselect(
                "喜欢的工艺类型", CRAFT_INTERESTS, default=["灰塑"],
                placeholder="请选择至少一种工艺", key="craft_interest_selection",
            )
            style_label = st.selectbox("讲解风格", list(STYLES), key="guide_style_selection")
        can_plan = selected_mode == "classic" or bool(interests)
        plan_button_label = "重新规划后续路线" if active_tour else "开始规划路线"
        if st.button(plan_button_label, type="primary", use_container_width=True, disabled=not can_plan, key="plan_route"):
            # During an active tour a duration-only control is interpreted as
            # remaining time and replanned from TourState.current_stop_id.
            # The ordinary route prompt is reserved for the initial route.
            request = _sidebar_plan_request(
                active_tour=active_tour,
                mode=selected_mode,
                interests=interests,
                style_label=style_label,
                duration=int(duration),
            )
            _send(adapter, request)
            st.rerun()
        if st.button("重置会话", use_container_width=True, key="reset_conversation"):
            adapter.reset()
            st.session_state.messages = []
            st.session_state.itinerary = adapter.itinerary
            st.session_state.tour_card_generated = False
            st.session_state.souvenir_show_map = False
            _start_session(adapter)
            st.rerun()


def _render_progress_panel(itinerary, messages: list[dict[str, object]]) -> None:
    """Render route and visitor-visible craft achievements side by side."""
    st.markdown(
        "<div class='achievement-dock'>"
        f"{_progress_panel_markup(itinerary)}{_craft_progress_markup(messages)}"
        "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="祠语智游", page_icon="🏛️", layout="wide",
        initial_sidebar_state="expanded",
    )
    _configure_environment()
    _begin_rag_warmup()
    background_image_data = _background_image_data()
    st.markdown("""<style>
    .stApp {background:#09191a;color:#2b2119;}
    [data-testid='stSpinner'] p,[data-testid='stSpinner'] span {color:#fff !important;text-shadow:0 1px 5px rgba(0,0,0,.9);}
    [data-testid='stSpinner'] svg {stroke:#fff !important;}
    .stApp:before {display:none;}
    [data-testid='stAppViewContainer'] {background:transparent !important;}
    [data-testid='stMain'] {position:relative;z-index:1;background-color:#09191a !important;background-image:linear-gradient(180deg,rgba(4,17,19,.08),rgba(20,10,7,.14)),url('data:image/png;base64,__BACKGROUND_IMAGE__') !important;background-size:cover !important;background-position:center bottom !important;background-repeat:no-repeat !important;background-attachment:fixed !important;}
    .stMainBlockContainer {position:relative;z-index:1;}
    header[data-testid='stHeader'],[data-testid='stToolbar'] {background:transparent !important;pointer-events:none;}
    header[data-testid='stHeader'] [data-testid='stExpandSidebarButton'] {pointer-events:auto;}
    .block-container {max-width:1180px;margin-top:0;padding:.85rem 1.1rem 4.8rem;border:0;background:transparent !important;box-shadow:none;}
    .block-container:before {display:none;}
    [data-testid='stBottom'],.stBottom {background:linear-gradient(180deg,transparent,rgba(5,21,22,.68) 42%,rgba(5,21,22,.88)) !important;padding-top:.6rem !important;padding-bottom:.05rem !important;min-height:0 !important;}
    [data-testid='stBottom'] > div,[data-testid='stBottom'] > div > div {padding-top:.15rem !important;padding-bottom:.05rem !important;margin-bottom:0 !important;min-height:0 !important;}
    [data-testid='stSidebar'] {background:linear-gradient(180deg,rgba(8,29,32,.985),rgba(31,17,14,.985));border-right:1px solid rgba(213,174,94,.55);box-shadow:10px 0 32px rgba(0,0,0,.32);}
    [data-testid='stSidebar'] h1,[data-testid='stSidebar'] h2,[data-testid='stSidebar'] h3,[data-testid='stSidebar'] label,[data-testid='stSidebar'] [data-testid='stWidgetLabel'] p,[data-testid='stSidebar'] [role='radiogroup'] p {color:#fff8ec !important;}
    [data-testid='stSidebar'] [data-testid='stCaptionContainer'] p {color:#d8c7b4 !important;opacity:1 !important;}
    [data-testid='stSidebar'] button[kind='secondary'] {color:#f5e9cc !important;background:linear-gradient(135deg,rgba(20,47,59,.9),rgba(65,29,27,.9)) !important;border:1px solid rgba(213,174,94,.5) !important;box-shadow:0 6px 18px rgba(0,0,0,.2);}
    [data-testid='stSidebar'] button[kind='secondary'] * {color:#f5e9cc !important;background:transparent !important;}
    [data-testid='stSidebar'] button[kind='primary'] {color:#fff8e8 !important;background:linear-gradient(110deg,#7e2925,#b56f35) !important;border:1px solid rgba(243,202,109,.68) !important;box-shadow:0 6px 20px rgba(103,29,25,.3),inset 0 1px 0 rgba(255,255,255,.12);}
    [data-testid='stSidebar'] button[kind='primary'] * {color:#fff8e8 !important;}
    [data-testid='stSidebar'] button[kind='primary']:hover,[data-testid='stSidebar'] button[kind='secondary']:hover {border-color:#55d7df !important;box-shadow:0 0 18px rgba(76,212,222,.2);}
    [data-testid='stSidebar'] .st-key-show_tour_map button {min-height:2.15rem;padding:.3rem .55rem;background:linear-gradient(120deg,rgba(116,43,30,.94),rgba(14,76,78,.94)) !important;border-color:rgba(225,183,89,.7) !important;font-size:.82rem;}
    [data-testid='stSidebar'] [data-testid='stNumberInput'] {max-width:14rem;}
    [data-testid='stSidebar'] [data-baseweb='select'] > div {background:linear-gradient(120deg,rgba(15,39,52,.96),rgba(52,25,25,.94)) !important;border:1px solid rgba(213,174,94,.48) !important;color:#fff8ec !important;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 5px 16px rgba(0,0,0,.18);}
    [data-testid='stSidebar'] [data-baseweb='select'] input,[data-testid='stSidebar'] [data-baseweb='select'] input::placeholder {color:#eadcbc !important;-webkit-text-fill-color:#eadcbc !important;}
    [data-testid='stSidebar'] [data-baseweb='select'] svg {fill:#dcb868 !important;color:#dcb868 !important;}
    [data-testid='stSidebar'] [data-baseweb='tag'] {background:linear-gradient(110deg,#792925,#a86131) !important;border:1px solid rgba(239,195,96,.58) !important;color:#fff6df !important;}
    [data-testid='stSidebar'] [data-baseweb='tag'] * {color:#fff6df !important;}
    [data-baseweb='popover'] [role='listbox'] {background:rgba(10,29,40,.98) !important;border:1px solid rgba(213,174,94,.5);box-shadow:0 12px 30px rgba(0,0,0,.4);}
    [data-baseweb='popover'] [role='option'] {color:#f4ead2 !important;}
    [data-baseweb='popover'] [role='option']:hover,[data-baseweb='popover'] [aria-selected='true'] {background:linear-gradient(90deg,rgba(123,42,36,.9),rgba(24,85,94,.9)) !important;color:#fff !important;}
    [data-testid='stSidebar'] [role='radiogroup'] input[type='radio'] {accent-color:#d4aa55;}
    [data-testid='stSidebar'] [role='radiogroup'] label:has(input:checked) p {color:#f4cc72 !important;text-shadow:0 0 10px rgba(244,204,114,.22);}
    [data-testid='stSidebar'] [data-testid='stSidebarCollapseButton'],[data-testid='stSidebar'] button[kind='header'] {background:#c99745 !important;border:1px solid #f4d98f !important;border-radius:.6rem !important;opacity:1 !important;}
    [data-testid='stSidebar'] [data-testid='stSidebarCollapseButton'] svg,[data-testid='stSidebar'] button[kind='header'] svg {fill:#fffdf8 !important;color:#fffdf8 !important;stroke:#fffdf8 !important;}
    [data-testid='stSidebarCollapseButton'] button,[data-testid='stExpandSidebarButton'],[data-testid='stSidebarCollapsedControl'],button[kind='headerNoPadding'][data-testid='stBaseButton-headerNoPadding'] {background:#c99745 !important;border:1px solid #f4d98f !important;border-radius:.6rem !important;opacity:1 !important;}
    [data-testid='stSidebarCollapseButton'] button svg,[data-testid='stExpandSidebarButton'] svg,[data-testid='stSidebarCollapsedControl'] svg,button[kind='headerNoPadding'][data-testid='stBaseButton-headerNoPadding'] svg {fill:#fffdf8 !important;color:#fffdf8 !important;stroke:#fffdf8 !important;}
    .sidebar-brand {position:relative;overflow:hidden;padding:1.15rem 1rem;margin:.15rem 0 1.25rem;border:1px solid rgba(229,190,105,.72);border-radius:4px 18px 4px 18px;background:linear-gradient(135deg,rgba(75,35,24,.94),rgba(9,49,52,.92));box-shadow:0 10px 28px rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.1),inset 0 0 24px rgba(204,157,66,.07);}
    .sidebar-brand:before {content:'◇';position:absolute;right:.65rem;top:.45rem;color:#e4bd68;font-size:.72rem;}
    .sidebar-brand:after {content:'';position:absolute;width:130px;height:1px;right:-12px;bottom:18px;background:linear-gradient(90deg,transparent,#54dce6);box-shadow:0 0 12px #54dce6;}
    [data-testid='stSidebar'] .sidebar-brand h1 {margin:0 0 .65rem;color:#fff8ec !important;font-size:1.18rem;line-height:1.55;letter-spacing:.02em;}
    [data-testid='stSidebar'] .sidebar-brand p {margin:0;color:#f8e8ce !important;font-size:.82rem;line-height:1.65;}
    div[data-testid='stElementContainer']:has(.progress-panel) {position:sticky;top:.35rem;z-index:40;}
    .achievement-dock {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:.65rem;margin:0 0 .7rem;}
    .progress-panel {position:relative;width:100%;box-sizing:border-box;padding:.62rem .82rem .68rem;border:1px solid rgba(178,131,48,.7);border-radius:4px 14px 4px 14px;background:linear-gradient(115deg,rgba(22,48,48,.97),rgba(58,29,21,.96));backdrop-filter:blur(18px);margin:0;overflow:hidden;box-shadow:0 8px 20px rgba(47,29,15,.22),inset 0 1px 0 rgba(255,255,255,.08);}
    .progress-panel:before {content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(68,218,231,.05),transparent);pointer-events:none;}
    .progress-panel.empty {display:flex;gap:.7rem;align-items:center;color:#d8c9ad;}.progress-panel.empty span {font-size:.9rem;}
    .progress-header {display:flex;justify-content:space-between;gap:.75rem;margin-bottom:.42rem;color:#f4ddb0;font-size:.8rem;}.progress-header span {color:#bfd2d5;}
    .progress-track {display:flex;gap:.2rem;min-width:max-content;padding:0 .1rem .05rem;}.progress-step {width:82px;position:relative;text-align:center;color:#91a6aa;font-size:.69rem;line-height:1.16;}.progress-step:not(:last-child):after {content:'';position:absolute;top:.4rem;left:58%;width:85%;height:1px;background:rgba(147,173,178,.35);z-index:0;}.progress-dot {position:relative;z-index:1;width:.96rem;height:.96rem;margin:0 auto .22rem;border-radius:50%;background:#102a38;display:grid;place-items:center;font-size:.58rem;border:1.5px solid #698c94;color:#9bc5ca;}.progress-step.completed,.progress-step.current {color:#f2dfb6;}.progress-step.completed .progress-dot {background:#b27a36;border-color:#e0b967;color:#fff;}.progress-step.current .progress-dot {background:#7d2824;border-color:#f0c36b;color:#fff;box-shadow:0 0 0 3px rgba(69,211,224,.13),0 0 12px rgba(69,211,224,.4);}.progress-step.completed:not(:last-child):after {background:linear-gradient(90deg,#c08a42,#42c9d3);}
    .route-progress-panel .progress-track {overflow-x:auto;scrollbar-width:thin;}.route-progress-panel .progress-step {width:82px;}
    .craft-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.32rem;}.craft-badge {display:flex;align-items:center;justify-content:center;gap:.3rem;min-height:1.55rem;border:1px solid rgba(119,151,153,.34);border-radius:4px 9px 4px 9px;background:rgba(5,25,29,.42);color:#8fa6a6;font-size:.7rem;}.craft-badge.unlocked {border-color:rgba(229,185,91,.72);background:linear-gradient(120deg,rgba(129,47,31,.82),rgba(18,91,91,.82));color:#fff0bf;box-shadow:0 0 10px rgba(66,205,213,.14);}.craft-symbol {color:#55ced6;font-weight:700;}.craft-badge.unlocked .craft-symbol {color:#f0c469;}
    .wechat-row {display:flex;align-items:flex-start;gap:.55rem;margin:.7rem 0;}.wechat-row.visitor {justify-content:flex-end;}.wechat-avatar {flex:0 0 2.3rem;height:2.3rem;border-radius:.65rem;display:grid;place-items:center;font-weight:700;color:#fff;background:linear-gradient(145deg,#a86d2d,#6f351d);border:1px solid rgba(240,198,105,.5);box-shadow:0 4px 14px rgba(0,0,0,.26);}.wechat-row.visitor .wechat-avatar {background:linear-gradient(145deg,#4f9d37,#267522);border-color:rgba(182,240,139,.7);}.wechat-bubble {max-width:min(88%,940px);padding:.62rem .82rem;border-radius:4px 14px 14px 14px;background:rgba(255,255,255,.96);border:1px solid rgba(255,255,255,.72);box-shadow:0 7px 20px rgba(0,0,0,.18);font-size:.95rem;line-height:1.55;color:#172630;}.wechat-row.visitor .wechat-bubble {border-radius:14px 4px 14px 14px;background:#95ec69;border-color:#79d852;color:#172314;}.wechat-speaker {font-size:.74rem;color:#8a6a45;margin-bottom:.18rem;}.wechat-row.visitor .wechat-speaker {color:#376328;}.wechat-service {margin-top:.42rem;padding-top:.35rem;border-top:1px solid rgba(156,116,65,.25);color:#765231;font-size:.82rem;}.wechat-row.visitor .wechat-service {border-color:rgba(47,116,31,.22);color:#315d27;}
    .detail-expansion-intro {display:block;margin:.12rem 0 .5rem;color:#7a542d;font-weight:700;}.detail-expansion-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.48rem;}.detail-expansion-card {min-height:5.7rem;padding:.58rem .65rem;border:1px solid rgba(174,119,45,.42);border-radius:4px 12px 4px 12px;background:linear-gradient(135deg,rgba(255,246,224,.94),rgba(230,242,237,.92));}.detail-expansion-card b {display:block;margin-bottom:.25rem;color:#8a4d1d;font-size:.88rem;letter-spacing:.04em;}.detail-expansion-card p {margin:0;color:#20313a;font-size:.84rem;line-height:1.62;}@media (max-width:700px) {.detail-expansion-grid {grid-template-columns:1fr;}}
    .chat-paragraph {display:block;text-indent:2em;margin:.12rem 0;}
    .tour-summary-card {position:relative;width:min(88%,940px);box-sizing:border-box;margin:1rem auto;padding:1.15rem 1.3rem 1rem;overflow:hidden;border:1px solid rgba(232,191,94,.82);border-radius:5px 22px 5px 22px;background:linear-gradient(135deg,rgba(72,28,22,.97),rgba(12,61,64,.96));color:#fff4d6;box-shadow:0 16px 38px rgba(0,0,0,.34),inset 0 0 0 3px rgba(255,255,255,.035);}
    .tour-end-record {width:min(72%,760px);box-sizing:border-box;margin:.45rem auto .65rem;padding:.72rem .9rem;border:1px solid rgba(232,191,94,.68);border-radius:4px 16px 4px 16px;background:linear-gradient(135deg,rgba(72,28,22,.92),rgba(12,61,64,.92));color:#f7ecd0;box-shadow:0 9px 24px rgba(0,0,0,.24);}.tour-end-record>div {display:flex;align-items:center;justify-content:space-between;gap:1rem;}.tour-end-record b {color:#efca76;font-size:.92rem;}.tour-end-record span,.tour-end-record p {color:#cbdad6;font-size:.72rem;}.tour-end-record p {margin:.35rem 0 0;padding-top:.35rem;border-top:1px solid rgba(232,191,94,.2);}
    .tour-summary-card:before {content:'';position:absolute;inset:9px;border:1px solid rgba(232,191,94,.2);border-radius:3px 15px 3px 15px;pointer-events:none;}.summary-seal {position:absolute;right:1.15rem;top:1rem;width:2.65rem;height:2.65rem;border:2px solid #e1b65e;border-radius:50%;display:grid;place-items:center;color:#f1ca75;font-size:.72rem;font-weight:700;transform:rotate(8deg);}.summary-kicker {color:#e7c476;font-size:.78rem;letter-spacing:.16em;text-align:center;}.tour-summary-card h2 {margin:.22rem 3rem .08rem;text-align:center;color:#fff5d8;font-family:'STKaiti','KaiTi','Microsoft YaHei',sans-serif;font-size:1.48rem;letter-spacing:.08em;}.summary-date {text-align:center;color:#e7c476;font-size:.68rem;}.summary-disclaimer {text-align:center;color:#b9ccca;font-size:.68rem;}.summary-stats {display:grid;grid-template-columns:repeat(4,1fr);gap:.45rem;margin:.7rem 0;}.summary-stats div {display:flex;flex-direction:column;align-items:center;padding:.5rem .25rem;border:1px solid rgba(225,183,90,.28);background:rgba(3,25,29,.32);}.summary-stats strong {color:#f1c66e;font-size:1.25rem;line-height:1.1;}.summary-stats span {margin-top:.2rem;color:#c8d8d5;font-size:.69rem;}.summary-section {margin-top:.52rem;}.summary-section>b {display:block;margin-bottom:.28rem;color:#efcc83;font-size:.76rem;}.summary-route,.summary-badges {display:flex;flex-wrap:wrap;gap:.32rem;}.summary-route-stop,.summary-badge {padding:.25rem .48rem;border:1px solid rgba(76,201,208,.32);border-radius:999px;background:rgba(4,30,34,.36);color:#d9e6e3;font-size:.7rem;}.summary-badge.unlocked {border-color:rgba(230,186,89,.48);color:#f2d591;}.summary-empty {color:#9eb4b2;font-size:.7rem;}.summary-wish {position:absolute;left:1rem;right:1rem;bottom:.55rem;padding-top:.38rem;border-top:1px solid rgba(231,190,96,.25);text-align:center;color:#e7d7b4;font-size:.72rem;}[data-testid='stDialog'] .tour-summary-card {width:100%;aspect-ratio:16/9;margin:.1rem auto .55rem;padding:.9rem 1rem 2.2rem;}div[role='dialog'] {width:min(720px,calc(100vw - 2rem)) !important;max-width:720px !important;background:linear-gradient(135deg,rgba(66,27,21,.99),rgba(7,55,58,.99)) !important;border:1px solid rgba(232,191,94,.82) !important;border-radius:6px 22px 6px 22px !important;box-shadow:0 22px 60px rgba(0,0,0,.52),inset 0 0 0 3px rgba(255,255,255,.035) !important;color:#fff4d6 !important;}
    div[role='dialog']>div,div[role='dialog'] [data-testid='stDialog'] {background:transparent !important;}
    div[role='dialog'] h1,div[role='dialog'] h2,div[role='dialog'] h3,div[role='dialog'] strong,div[role='dialog'] p,div[role='dialog'] label {color:#fff1cf !important;}
    div[role='dialog'] button {color:#fff4d6 !important;background:linear-gradient(120deg,rgba(116,43,30,.96),rgba(14,76,78,.96)) !important;border:1px solid rgba(225,183,89,.68) !important;}
    div[role='dialog'] button svg {fill:#f3d27f !important;color:#f3d27f !important;}
    div[role='dialog']:has(.photo-hint-card-marker) {width:min(980px,calc(100vw - 2rem)) !important;max-width:980px !important;background:linear-gradient(135deg,rgba(66,27,21,.99),rgba(7,55,58,.99)) !important;border:1px solid rgba(232,191,94,.82) !important;border-radius:6px 22px 6px 22px !important;box-shadow:0 22px 60px rgba(0,0,0,.52),inset 0 0 0 3px rgba(255,255,255,.035) !important;color:#fff4d6 !important;}
    div[role='dialog']:has(.photo-hint-card-marker) h2,div[role='dialog']:has(.photo-hint-card-marker) h3,div[role='dialog']:has(.photo-hint-card-marker) strong,div[role='dialog']:has(.photo-hint-card-marker) p {color:#fff1cf !important;}
    div[role='dialog']:has(.photo-hint-card-marker) h3 {color:#efc96f !important;font-family:'STKaiti','KaiTi','Microsoft YaHei',sans-serif;letter-spacing:.08em;}
    div[role='dialog']:has(.photo-hint-card-marker) [data-testid='stImage'] {padding:.42rem;background:rgba(255,248,222,.94);border:1px solid rgba(232,191,94,.72);border-radius:4px 15px 4px 15px;box-shadow:0 10px 28px rgba(0,0,0,.28);}
    div[role='dialog']:has(.photo-hint-card-marker) [data-testid='stImage'] img {display:block;width:100%;border-radius:2px 10px 2px 10px;}
    div[role='dialog']:has(.photo-hint-card-marker) [data-testid='stImage'] [data-testid='stCaptionContainer'] p {color:#72522d !important;text-shadow:none !important;font-size:.72rem !important;}
    [data-testid='stDialog'] div[role='dialog']:has(.photo-hint-card-marker),[data-baseweb='modal'] div[role='dialog']:has(.photo-hint-card-marker) {padding:1rem 1.15rem 1.05rem !important;background-color:#102f31 !important;background-image:linear-gradient(118deg,#421d19 0%,#2d211d 42%,#0b3d40 100%) !important;}
    [data-testid='stDialog'] div[role='dialog']:has(.photo-hint-card-marker)>div,[data-baseweb='modal'] div[role='dialog']:has(.photo-hint-card-marker)>div {background:transparent !important;}
    .st-key-photo_guide_card {position:relative;box-sizing:border-box;width:100%;aspect-ratio:16/9;min-height:430px;padding:1.25rem 1.35rem 1.1rem;margin:.05rem 0 .65rem;border:2px solid #d9ae54;border-radius:5px 22px 5px 22px;background:linear-gradient(120deg,rgba(64,28,23,.97),rgba(10,55,58,.97));box-shadow:inset 0 0 0 8px rgba(5,21,23,.18),inset 0 0 0 9px rgba(220,174,79,.34),0 14px 34px rgba(0,0,0,.32);overflow:hidden;}
    .st-key-photo_guide_card:before {content:'';position:absolute;inset:9px;border:1px solid rgba(231,186,91,.52);border-radius:3px 15px 3px 15px;pointer-events:none;}
    .st-key-photo_guide_card:after {content:'';position:absolute;inset:0;pointer-events:none;opacity:.13;background:radial-gradient(circle at 12% 18%,rgba(231,190,95,.34),transparent 28%),radial-gradient(circle at 88% 82%,rgba(60,211,218,.26),transparent 30%);}
    .st-key-photo_guide_card>div {position:relative;z-index:1;}
    .photo-card-heading {text-align:center;margin:0 0 .8rem;}
    .photo-card-heading span {display:block;color:#e8bd62;font-size:.76rem;font-weight:700;letter-spacing:.2em;}
    .photo-card-heading h3 {margin:.18rem 0 .08rem !important;color:#fff0ca !important;font-family:'STKaiti','KaiTi','Microsoft YaHei',sans-serif;font-size:1.45rem !important;letter-spacing:.08em;}
    .photo-card-heading small {color:#a9c8c6;font-size:.7rem;}
    .st-key-photo_guide_card strong {display:block;margin-bottom:.2rem;color:#e7bd62 !important;font-size:.78rem;}
    .st-key-photo_guide_card p {color:#edf1e8 !important;font-size:.8rem;line-height:1.55;}
    .st-key-photo_guide_card [data-testid='stImage'] {padding:.34rem !important;background:rgba(255,246,214,.94) !important;border:1px solid rgba(226,183,88,.76) !important;border-radius:4px 14px 4px 14px !important;}
    .st-key-photo_pose_panel {width:93%;margin:-.45rem auto 0;}
    .st-key-photo_pose_panel [data-testid='stImage'] {width:100%;margin:0 auto;}
    .st-key-photo_advice_panel {width:100%;display:flex;align-items:center;justify-content:center;}
    .st-key-photo_advice_panel>div {width:100%;}
    .photo-advice-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem;height:100%;align-content:center;}
    .photo-advice-grid section {position:relative;min-height:112px;box-sizing:border-box;padding:.85rem .9rem;border:1px solid rgba(226,181,82,.62);border-radius:4px 15px 4px 15px;background:linear-gradient(135deg,rgba(76,34,25,.54),rgba(5,49,53,.7));box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 6px 16px rgba(0,0,0,.2);overflow:hidden;}
    .photo-advice-grid section:after {content:'';position:absolute;right:-18px;bottom:-20px;width:62px;height:62px;border:1px solid rgba(67,205,214,.18);border-radius:50%;box-shadow:0 0 16px rgba(67,205,214,.1);}
    .photo-advice-grid b {display:block;margin-bottom:.42rem;color:#efc96f;font-size:.92rem;letter-spacing:.06em;}
    .photo-advice-grid p {margin:0;color:#f3eee0 !important;font-size:.88rem !important;line-height:1.65 !important;}
    @media (max-width:700px) {.st-key-photo_guide_card {aspect-ratio:auto;min-height:0;padding:1rem .8rem;}.photo-card-heading h3 {font-size:1.2rem !important;}.photo-advice-grid {grid-template-columns:1fr;}.photo-advice-grid section {min-height:0;}div[role='dialog']:has(.photo-hint-card-marker) {width:calc(100vw - 1rem) !important;}}
    .stMain h4 {display:flex;align-items:center;justify-content:center;gap:.8rem;color:#fff1c8;text-shadow:0 2px 12px rgba(0,0,0,.65);letter-spacing:.08em;font-family:'STKaiti','KaiTi','Microsoft YaHei',sans-serif;font-size:1.42rem;}
    .stMain h4:before,.stMain h4:after {content:'';width:72px;height:1px;background:linear-gradient(90deg,transparent,#a8762f,#36bfc8);}
    .stMain h4:after {transform:scaleX(-1);}
    .stMain [data-testid='stCaptionContainer'] p {color:#e8dbbd !important;text-shadow:0 1px 8px rgba(0,0,0,.7);}
    .st-key-tour_chat_wallpaper {background:transparent !important;border:0 !important;border-radius:0 !important;box-shadow:none !important;}
    .st-key-tour_chat_wallpaper > div,.st-key-tour_chat_wallpaper [data-testid='stVerticalBlockBorderWrapper'],.st-key-tour_chat_wallpaper [data-testid='stVerticalBlock'] {background:transparent !important;border:0 !important;border-color:transparent !important;box-shadow:none !important;}
    .stMain [data-testid='stVerticalBlockBorderWrapper'] ::-webkit-scrollbar {width:7px;}.stMain [data-testid='stVerticalBlockBorderWrapper'] ::-webkit-scrollbar-thumb {background:linear-gradient(#4ed6df,#bb8240);border-radius:10px;}
    .stMain button {border:1px solid rgba(179,132,48,.68);border-radius:4px 13px 4px 13px;background:linear-gradient(135deg,rgba(79,36,25,.96),rgba(11,71,73,.96));color:#fff8e8;box-shadow:0 6px 18px rgba(56,31,17,.2),inset 0 1px 0 rgba(255,255,255,.1);}
    .stMain button:hover {border-color:#57d8e2;color:#fff;box-shadow:0 0 18px rgba(74,211,224,.2);}
    [data-testid='stChatInput'] {background:rgba(255,251,232,.98);border:1px solid rgba(184,137,54,.68);border-radius:4px 16px 4px 16px;box-shadow:0 8px 26px rgba(61,37,18,.2);}
    .st-key-inline_chat_input {margin-top:.25rem;padding:0;background:transparent !important;}
    .st-key-inline_chat_input [data-testid='stChatInput'] {width:100%;margin:0;background:rgba(255,251,232,.98);}
    @media (max-width: 700px) {[data-testid='stMain'] {background-position:62% bottom !important;}.block-container {margin-top:0;padding:.65rem .75rem 6.5rem;}.achievement-dock {grid-template-columns:1fr;}.progress-track {overflow-x:auto;}.progress-header {display:block;}.progress-header span {display:block;margin-top:.25rem;}.progress-panel.empty {align-items:flex-start;flex-direction:column;gap:.25rem;}.stMain h4:before,.stMain h4:after {width:28px;}.tour-summary-card {width:96%;padding:1rem .8rem;}.summary-stats {grid-template-columns:repeat(2,1fr);}.summary-seal {width:2.2rem;height:2.2rem;}}
    </style>""".replace("__BACKGROUND_IMAGE__", background_image_data), unsafe_allow_html=True)
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
    _render_progress_panel(itinerary, st.session_state.messages)
    tour_finished = bool(getattr(itinerary, "is_finished", False))
    finished_early = bool(getattr(itinerary, "finished_early", False))
    # Compatibility with adapters created before the explicit completion flag.
    if not tour_finished:
        tour_finished = bool(
            itinerary.total_count
            and itinerary.completed_count >= itinerary.total_count
            and itinerary.remaining_count == 0
        )
    if not tour_finished:
        st.session_state.tour_card_generated = False
        st.session_state.souvenir_show_map = False

    _render_route_sidebar(adapter)

    st.markdown("#### 与导游对话")
    with st.container(height=460, border=False, key="tour_chat_wallpaper"):
        closing_ack_rendered = False
        for item in st.session_state.messages:
            item_text = str(item.get("content") or "")
            is_closing_item = (
                item.get("scene_kind") == "tour_closing"
                or "最后一站已确认完成" in item_text
                or "本次导览已结束" in item_text
            )
            if tour_finished and is_closing_item:
                if not closing_ack_rendered:
                    _render_chat_message(
                        {
                            "role": "assistant",
                            "scene_kind": "tour_closing",
                            "content": (
                                "本次导览已提前结束，已为您保留实际参观记录。"
                                if finished_early
                                else "最后一站已确认完成，本次导览已结束。"
                            ),
                        }
                    )
                    closing_ack_rendered = True
                continue
            _render_chat_message(item)
        if tour_finished and not closing_ack_rendered:
            _render_chat_message(
                {
                    "role": "assistant",
                    "scene_kind": "tour_closing",
                    "content": (
                        "本次导览已提前结束，已为您保留实际参观记录。"
                        if finished_early
                        else "最后一站已确认完成，本次导览已结束。"
                    ),
                }
            )
    if tour_finished:
        st.markdown(
            _tour_end_record_markup(itinerary, finished_early=finished_early),
            unsafe_allow_html=True,
        )
    st.caption(
        "本次导览已完成，您仍可以继续询问陈家祠或周边游玩问题。"
        if tour_finished else "您可以直接提问，或使用快捷指令推进导览。"
    )
    columns = st.columns(3 if tour_finished else len(QUICK_ACTIONS))
    if tour_finished:
        if columns[0].button("查看游览地图", use_container_width=True, key="closing_map"):
            _show_tour_map()
        card_button_label = (
            "查看纪念卡" if st.session_state.get("tour_card_generated", False) else "生成纪念卡"
        )
        if columns[1].button(card_button_label, use_container_width=True, key="closing_card"):
            if not st.session_state.get("tour_card_generated", False):
                with st.spinner("正在生成纪念卡…"):
                    _tour_souvenir_svg(itinerary, st.session_state.messages)
                    st.session_state.tour_card_generated = True
            st.session_state.souvenir_show_map = False
            _show_souvenir_card(itinerary, st.session_state.messages)
        if columns[2].button("附近美食推荐", use_container_width=True, key="closing_food"):
            _send(adapter, "请推荐一些陈家祠附近的美食。")
            st.rerun()
    else:
        for column, action in zip(columns, QUICK_ACTIONS):
            if column.button(action, use_container_width=True):
                if action == "拍照提示":
                    with st.spinner("正在准备拍照建议…"):
                        reply = adapter.send(action)
                    photo_text = "\n\n".join(
                        message.text for message in reply.messages if message.text.strip()
                    )
                    _show_photo_hint_card(photo_text, itinerary.current_stop)
                    continue
                _send(adapter, action)
                st.rerun()
    with st.container(key="inline_chat_input"):
        input_hint = (
            "游览结束了，还可以继续问我陈家祠或附近游玩问题"
            if tour_finished else "例如：这里最值得看什么？"
        )
        if prompt := st.chat_input(input_hint, max_chars=200):
            _send(adapter, prompt)
            st.rerun()


if __name__ == "__main__":
    main()
