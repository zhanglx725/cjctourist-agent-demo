"""Deterministic C8 controls for explicitly stated extended preferences.

This module deliberately recognises only narrow, user-facing commands.  It
does not infer age, relationship, occupation or expertise from conversational
wording, and it never imports TourState, routes, RAG or AgentState.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from guidance_policy import build_guidance_policy
from visitor_profile import (
    DEFAULT_AUDIENCE_MODE,
    DEFAULT_EXPLANATION_STYLE,
    DEFAULT_INTERACTION_MODE,
    DEFAULT_KNOWLEDGE_LEVEL,
    VisitorProfileError,
    create_visitor_profile,
    profile_from_dict,
    update_visitor_profile,
)


EXTENDED_DEFAULT_PATCH = {
    "audience_mode": DEFAULT_AUDIENCE_MODE,
    "knowledge_level": DEFAULT_KNOWLEDGE_LEVEL,
    "explanation_style": DEFAULT_EXPLANATION_STYLE,
    "interaction_mode": DEFAULT_INTERACTION_MODE,
}


@dataclass(frozen=True)
class ExtendedProfileControl:
    """One audited C8 command suggestion, before any state is mutated."""

    kind: str  # update / view / reset / delete / none / clarification
    patch: dict[str, str]
    reexpress_current: bool = False
    message: str | None = None


def _matches(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def parse_extended_profile_control(text: str) -> ExtendedProfileControl:
    """Convert explicit Chinese requests into a validated-profile patch.

    A vague collective word such as ``我们`` is intentionally insufficient;
    only phrases that explicitly ask for a supported guidance mode are used.
    """
    value = (text or "").strip()
    if not value:
        return ExtendedProfileControl("none", {})
    if _matches(value, ("查看当前画像", "查看我的偏好", "当前讲解偏好", "我的导览偏好")):
        return ExtendedProfileControl("view", {})
    if _matches(value, ("删除本次偏好", "清除本次偏好", "删除会话偏好")):
        return ExtendedProfileControl("delete", {})
    if _matches(value, ("恢复标准讲解", "恢复默认讲解", "恢复中性讲解")):
        return ExtendedProfileControl("reset", dict(EXTENDED_DEFAULT_PATCH))

    candidates: dict[str, set[str]] = {}
    def add(field: str, choice: str, phrases: tuple[str, ...]) -> None:
        if _matches(value, phrases):
            candidates.setdefault(field, set()).add(choice)

    add("audience_mode", "child_friendly", ("给小朋友讲", "按儿童方式讲", "儿童友好讲解"))
    add("audience_mode", "family", ("我们是亲子参观", "按亲子方式讲", "家庭参观讲解"))
    add("audience_mode", "study", ("按研学方式讲", "用于研学", "研学讲解"))
    add("audience_mode", "mixed_group", ("混合群体讲解", "不同基础一起听", "兼顾不同基础"))
    add("knowledge_level", "professional", ("我是建筑专业的", "我是专业人士", "按专业水平讲"))
    add("knowledge_level", "enthusiast", ("按爱好者水平讲", "我是工艺爱好者"))
    add("explanation_style", "story", ("用故事方式讲", "故事方式讲", "多讲故事"))
    add("explanation_style", "technical", ("用技术方式讲", "技术方式讲"))
    add("explanation_style", "interactive", ("互动方式讲", "多一点互动"))
    add("explanation_style", "expert", ("讲得专业一点", "专业一点", "用专家方式讲", "专家方式讲"))
    add("interaction_mode", "listen_only", ("不要再问我问题", "只听讲解", "不要互动"))
    add("interaction_mode", "interactive_tasks", ("给我观察任务", "安排互动任务"))

    conflict = [field for field, choices in candidates.items() if len(choices) > 1]
    if conflict:
        return ExtendedProfileControl(
            "clarification", {}, message="这句话同时包含同一项偏好的多个选择，请一次只确认一种讲解方式。"
        )
    patch = {field: next(iter(choices)) for field, choices in candidates.items()}
    reexpress = _matches(value, ("按新方式重新讲当前内容", "重新讲当前内容", "按新方式再讲一遍"))
    if reexpress and not patch:
        return ExtendedProfileControl("clarification", {}, message="请先明确希望改成哪种讲解方式，再重新讲当前内容。")
    return ExtendedProfileControl("update" if patch else "none", patch, reexpress_current=reexpress)


def apply_extended_profile_control(
    profile_data: dict[str, Any] | None, text: str
) -> dict[str, Any]:
    """Apply C8 immutably and return policy audit data, never tour state."""
    control = parse_extended_profile_control(text)
    if control.kind in {"none", "clarification"}:
        return {"ok": False, "control": control, "profile": profile_data, "policy": None,
                "message": control.message or "请明确选择一种讲解偏好。"}
    profile = profile_from_dict(profile_data) if profile_data else create_visitor_profile()
    if control.kind == "view":
        return {"ok": True, "control": control, "profile": profile.to_dict(),
                "policy": build_guidance_policy(profile).to_dict(), "changed": False,
                "message": "已读取本次会话的讲解偏好。"}
    if control.kind == "delete":
        return {"ok": True, "control": control, "profile": None, "policy": None,
                "changed": True, "message": "已清除本次会话的讲解偏好；当前路线和游览进度保持不变。"}
    try:
        updated = update_visitor_profile(profile, **control.patch)
    except VisitorProfileError as exc:
        return {"ok": False, "control": control, "profile": profile_data, "policy": None,
                "message": f"偏好设置无效，未做任何更新：{exc}"}
    return {"ok": True, "control": control, "profile": updated.to_dict(),
            "policy": build_guidance_policy(updated).to_dict(), "changed": True,
            "message": "已更新本次会话的讲解偏好；后续讲解会使用新设置。"}
