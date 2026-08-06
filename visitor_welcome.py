"""Versioned, one-time bilingual welcome shown when a visitor opens a thread."""

from __future__ import annotations


WELCOME_VERSION = "visitor_welcome_v1"
WELCOME_MESSAGE = """亲爱的游客，欢迎来到陈家祠，我是小祠，您的专属导游，很高兴为您服务。
您可以输入您想要的语言，开启您的陈家祠探索之旅。我们提供经典模式和定制模式。如果您想马上开启参观，您可以选择经典模式。如果您想有一段与众不同的游览经历，您可以选择定制模式。在定制模式中，你可以选择工艺偏好和讲解风格，祝您游览愉快！请问您选择什么语言呢？

Dear visitors, welcome to the Chen Clan Academy. I'm Xiao Ci, your personal tour guide, and it’s my great pleasure to be at your service.

You may input your preferred language to kick off your journey exploring the Chen Clan Academy. We provide two tour modes: Classic Mode and Custom Mode. Pick Classic Mode if you want to start your tour immediately. Choose Custom Mode for a one-of-a-kind sightseeing experience. Within Custom Mode, you are able to select your favoured craft themes and narration style. Enjoy your visit! Which language would you prefer?"""

LANGUAGE_PROMPT = """请问您选择什么语言呢？例如中文、英语或韩语，也可以输入其他语言。

Which language would you prefer? For example, Chinese, English, or Korean. You may also enter another language."""

LANGUAGE_REQUIRED_PROMPT = """请先选择语言哦。

Please select a language first."""

MODE_PROMPT = "请选择“经典模式”或“定制模式”。经典模式可以快速开始参观；定制模式可以继续选择工艺偏好和讲解风格。"

def initialize_visitor_welcome() -> dict[str, object]:
    return {
        "schema_version": WELCOME_VERSION,
        "status": "awaiting_language",
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
