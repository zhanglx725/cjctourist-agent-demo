"""Versioned, one-time bilingual welcome shown when a visitor opens a thread."""

from __future__ import annotations


WELCOME_VERSION = "visitor_welcome_v1"
WELCOME_MESSAGE = """亲爱的游客，欢迎来到陈家祠，我是小祠，您的专属导游，很高兴为您服务。
您可以输入您想要的语言，开启您的陈家祠探索之旅。我们提供经典模式和定制模式。如果您想马上开启参观，您可以选择经典模式。如果您想有一段与众不同的游览经历，您可以选择定制模式。在定制模式中，你可以选择工艺偏好和讲解风格，祝您游览愉快！您准备好了吗？

Dear visitors, welcome to the Chen Clan Academy. I'm Xiao Ci, your personal tour guide, and it’s my great pleasure to be at your service.

You may input your preferred language to kick off your journey exploring the Chen Clan Academy. We provide two tour modes: Classic Mode and Custom Mode. Pick Classic Mode if you want to start your tour immediately. Choose Custom Mode for a one-of-a-kind sightseeing experience. Within Custom Mode, you are able to select your favoured craft themes and narration style. Enjoy your visit! Are you ready?"""

LANGUAGE_PROMPT = """请选择您需要的讲解语言，例如中文、英语、韩语，也可以输入其他语言。

Please enter your preferred narration language, such as Chinese, English, or Korean. You may also enter another language."""

READY_PROMPT = """您准备好后，请回复“准备好了”。

When you are ready, please reply “I'm ready”."""

MODE_PROMPT = """请选择“经典模式”或“定制模式”。经典模式可以快速开始参观；定制模式可以继续选择工艺偏好和讲解风格。

Please choose Classic Mode or Custom Mode. Classic Mode starts the visit quickly, while Custom Mode lets you continue choosing craft preferences and narration style."""

READY_RESPONSES = frozenset({
    "准备好了", "我准备好了", "准备好啦", "准备好咯", "好了", "好的", "好",
    "开始吧", "可以开始了", "可以", "ready", "i'm ready", "im ready",
    "i am ready", "yes", "let's go", "lets go", "start",
})
NOT_READY_RESPONSES = frozenset({
    "还没准备好", "没有准备好", "没准备好", "稍等", "等一下",
    "not ready", "i'm not ready", "im not ready", "wait",
})


def initialize_visitor_welcome() -> dict[str, object]:
    return {
        "schema_version": WELCOME_VERSION,
        "status": "awaiting_ready",
        "play_count": 1,
    }


def visitor_welcome_already_played(program: object) -> bool:
    return bool(
        isinstance(program, dict)
        and program.get("schema_version") == WELCOME_VERSION
        and program.get("status") in {
            "awaiting_ready", "awaiting_language", "awaiting_mode", "completed",
        }
    )


def is_ready_response(text: str) -> bool:
    compact = " ".join(str(text or "").strip().casefold().rstrip("。！!？?").split())
    if compact in NOT_READY_RESPONSES:
        return False
    return compact in READY_RESPONSES


def is_not_ready_response(text: str) -> bool:
    compact = " ".join(str(text or "").strip().casefold().rstrip("。！!？?").split())
    return compact in NOT_READY_RESPONSES


def is_language_skip(text: str) -> bool:
    compact = " ".join(str(text or "").strip().casefold().rstrip("。！!？?").split())
    return compact in {"跳过", "默认", "都可以", "无所谓", "skip", "default", "any"}
