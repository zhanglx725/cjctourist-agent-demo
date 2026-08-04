"""Deterministic C2 collection of explicitly stated visitor preferences.

The module does not plan a route and does not touch TourState.  Its collection
metadata records only which active profile fields have been explicitly resolved;
the preference values themselves live in one C1 VisitorProfile instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duration_parser import parse_duration_minutes
from visitor_profile import (
    DEFAULT_AVAILABLE_MINUTES,
    DEFAULT_DETAIL_LEVEL,
    VisitorProfile,
    VisitorProfileError,
    create_visitor_profile,
    profile_from_dict,
    update_visitor_profile,
)


PROFILE_FIELD_ORDER = ("available_minutes", "interests", "detail_level")
COLLECTION_FIELD_ORDER = (
    "available_minutes", "interests", "detail_level", "explanation_style", "language",
)
CLASSIC_PROFILE_FIELDS = ("available_minutes",)
CUSTOM_PROFILE_FIELDS = (
    "available_minutes", "interests", "explanation_style", "language",
)
INTEREST_TERMS = (
    "建筑装饰", "灰塑", "木雕", "石雕", "砖雕", "陶塑", "三国", "故事", "吉祥", "工艺",
)
NEUTRAL_TERMS = ("都可以", "不确定", "随便", "没特别偏好")
QUESTION_TERMS = ("什么", "为什么", "介绍", "特点", "怎么", "如何", "？", "?")
MINIMIZE_WALKING_TERMS = (
    "少走路",
    "少走一点",
    "少走些",
    "尽量少走",
    "步行最少",
    "不想走太多",
    "不要走太多",
)
SKIP_TERMS = ("跳过", "默认", "都可以", "无所谓", "没有偏好")


class ProfileDialogueError(ValueError):
    """Raised only for malformed persisted collection metadata."""


@dataclass(frozen=True)
class ProfileCollection:
    profile: VisitorProfile
    resolved_fields: tuple[str, ...] = ()
    status: str = "collecting"
    required_fields: tuple[str, ...] = PROFILE_FIELD_ORDER

    def __post_init__(self) -> None:
        invalid = set(self.resolved_fields).difference(COLLECTION_FIELD_ORDER)
        if invalid:
            raise ProfileDialogueError(f"画像收集状态含未知字段：{', '.join(sorted(invalid))}")
        if self.status not in {"collecting", "ready"}:
            raise ProfileDialogueError("画像收集状态无效。")
        invalid_required = set(self.required_fields).difference(COLLECTION_FIELD_ORDER)
        if invalid_required or not self.required_fields:
            raise ProfileDialogueError("画像收集所需字段无效。")
        object.__setattr__(self, "required_fields", tuple(
            field for field in COLLECTION_FIELD_ORDER if field in self.required_fields
        ))
        object.__setattr__(self, "resolved_fields", tuple(
            field for field in COLLECTION_FIELD_ORDER if field in self.resolved_fields
        ))
        expected_status = "ready" if all(
            field in self.resolved_fields for field in self.required_fields
        ) else "collecting"
        if self.status != expected_status:
            raise ProfileDialogueError("画像收集状态与已解决字段不一致。")

    @property
    def next_missing_field(self) -> str | None:
        return next((field for field in self.required_fields if field not in self.resolved_fields), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "resolved_fields": list(self.resolved_fields),
            "status": self.status,
            "required_fields": list(self.required_fields),
            "next_missing_field": self.next_missing_field,
        }


@dataclass(frozen=True)
class ProfileCollectionResult:
    status: str
    collection: ProfileCollection
    message: str
    patch: dict[str, Any]
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profile_collection": self.collection.to_dict(),
            "visitor_profile": self.collection.profile.to_dict(),
            "message": self.message,
            "patch": dict(self.patch),
            "reason_code": self.reason_code,
        }


def new_profile_collection(
    initial_profile: VisitorProfile | None = None,
    *,
    required_fields: tuple[str, ...] = PROFILE_FIELD_ORDER,
) -> ProfileCollection:
    """Start an empty collection; C1 defaults are not treated as user input."""
    return ProfileCollection(
        profile=initial_profile or create_visitor_profile(),
        required_fields=required_fields,
    )


def collection_from_dict(
    value: dict[str, Any] | None,
    initial_profile: VisitorProfile | None = None,
    *,
    required_fields: tuple[str, ...] | None = None,
) -> ProfileCollection:
    if value is None:
        return new_profile_collection(
            initial_profile, required_fields=required_fields or PROFILE_FIELD_ORDER
        )
    if not isinstance(value, dict) or not isinstance(value.get("profile"), dict):
        raise ProfileDialogueError("画像收集状态格式无效。")
    return ProfileCollection(
        profile=profile_from_dict(value["profile"]),
        resolved_fields=tuple(value.get("resolved_fields", [])),
        status=str(value.get("status", "collecting")),
        required_fields=tuple(value.get("required_fields", required_fields or PROFILE_FIELD_ORDER)),
    )


def _prompt(field: str) -> str:
    return {
        "available_minutes": "您有多少分钟可用于游览？例如“30分钟”。",
        "interests": "您更想看什么？例如“灰塑和木雕”；如果没有特别偏好，可以说“都可以”。",
        "detail_level": "您希望怎样讲解？可说“简单讲讲”“标准讲解”或“想深入学习”。",
        "explanation_style": "您喜欢哪种讲解风格？可输入“标准、故事、技术、互动或专家”，也可以说“跳过”。",
        "language": "您需要哪种讲解语言？例如中文、英语、韩语，也可以输入其他语言或说“跳过”。",
    }[field]


def _explanation_style_candidate(text: str) -> str | None:
    aliases = {
        "story": ("故事", "叙事"), "technical": ("技术", "工艺原理"),
        "interactive": ("互动", "问答"), "expert": ("专家", "专业"),
        "standard": ("标准", "自然", "普通"),
    }
    matches = [value for value, terms in aliases.items() if any(term in text for term in terms)]
    return matches[0] if len(set(matches)) == 1 else None


def _language_candidate(text: str, *, allow_free_text: bool = False) -> str | None:
    aliases = {
        "zh": ("中文", "普通话", "汉语", "mandarin", "chinese"),
        "en": ("英语", "英文", "english"),
        "ko": ("韩语", "韩文", "한국어", "korean"),
        "ja": ("日语", "日文", "日本語", "japanese"),
        "yue": ("粤语", "广东话", "cantonese"),
        "fr": ("法语", "法文", "french"), "de": ("德语", "德文", "german"),
        "es": ("西班牙语", "spanish"),
    }
    lowered = text.casefold()
    if any(term in text for term in SKIP_TERMS):
        return None
    matches = [value for value, terms in aliases.items() if any(term.casefold() in lowered for term in terms)]
    if len(set(matches)) == 1:
        return matches[0]
    candidate = text.strip().strip("。.!！")
    if allow_free_text and 1 < len(candidate) <= 40 and (
        candidate.endswith(("语", "文"))
        or (candidate.isascii() and all(char.isalpha() or char in " -" for char in candidate))
    ):
        return candidate
    return None


def _detail_candidates(text: str, *, allow_bare_detail: bool = False) -> set[str]:
    candidates: set[str] = set()
    if any(term in text for term in ("简单讲", "简要", "简短", "快一点")):
        candidates.add("short")
    deep_terms = ["深入学习", "深入", "深度", "详细讲", "讲细"]
    if allow_bare_detail:
        # A compact route profile such as “30min路线，木雕，详细” may use the
        # adjective by itself.  Keep this shorthand inside C2 collection so it
        # cannot turn “再讲详细一点” at a physical stop into a persistent C4
        # profile update.
        deep_terms.append("详细")
    if any(term in text for term in deep_terms):
        candidates.add("deep")
    if any(term in text for term in ("标准讲", "正常讲", "适中")):
        candidates.add("standard")
    return candidates


def _extract_patch(
    text: str,
    *,
    allow_bare_detail: bool = False,
    current_field: str | None = None,
) -> tuple[dict[str, Any], set[str], str | None]:
    """Extract one atomic patch; conflicting fields reject the whole turn."""
    duration = parse_duration_minutes(text)
    detail = _detail_candidates(text, allow_bare_detail=allow_bare_detail)
    if duration.reason_code == "ambiguous_duration":
        return {}, set(), "时间表达包含多个不同分钟数，请只确认一个可用时间。"
    if len(detail) > 1:
        return {}, set(), "讲解深度表达不一致，请选择简单、标准或深入其中一种。"
    patch: dict[str, Any] = {}
    fields: set[str] = set()
    if duration.ok:
        patch["available_minutes"] = duration.minutes
        fields.add("available_minutes")
    interests = [
        term for term in INTEREST_TERMS if term in text
    ] if current_field in {None, "available_minutes", "interests"} else []
    if interests:
        patch["interests"] = interests
        fields.add("interests")
    if detail:
        patch["detail_level"] = next(iter(detail))
        fields.add("detail_level")
    style = _explanation_style_candidate(text)
    if style:
        patch["explanation_style"] = style
        fields.add("explanation_style")
    language = _language_candidate(text, allow_free_text=current_field == "language")
    if language:
        patch["language"] = language
        fields.add("language")
    if any(term in text for term in MINIMIZE_WALKING_TERMS):
        # This optional route preference is stored in the one VisitorProfile
        # but never becomes a fourth required collection question.
        patch["route_constraint"] = "minimize_walking"
    return patch, fields, None


def extract_profile_patch(user_text: str) -> tuple[dict[str, Any], set[str], str | None]:
    """Expose C2's deterministic synonym parser for controlled C4 updates.

    This deliberately returns only a candidate patch.  Callers must still use
    C1's immutable ``update_visitor_profile`` for validation and must decide
    whether the surrounding dialogue is actually an update request.
    """
    return _extract_patch(user_text)


def _neutral_value(field: str) -> Any:
    return {
        "available_minutes": DEFAULT_AVAILABLE_MINUTES,
        "interests": [],
        "detail_level": DEFAULT_DETAIL_LEVEL,
        "explanation_style": "standard",
        "language": None,
    }[field]


def collect_profile_input(
    collection_data: dict[str, Any] | None,
    user_text: str,
    *,
    start_collection: bool = False,
    base_profile: VisitorProfile | dict[str, Any] | None = None,
    required_fields: tuple[str, ...] | None = None,
) -> ProfileCollectionResult | None:
    """Process one route-profile turn without invoking an LLM or a planner.

    ``None`` means this text is not part of profile collection and must remain
    available to the existing route/RAG/event router.
    """
    initial_profile = (
        base_profile if isinstance(base_profile, VisitorProfile)
        else profile_from_dict(base_profile) if isinstance(base_profile, dict) else None
    )
    required = required_fields or PROFILE_FIELD_ORDER
    collection = (
        collection_from_dict(collection_data, initial_profile, required_fields=required)
        if collection_data else None
    )
    active = collection is not None and collection.status == "collecting"
    if not active and not start_collection:
        return None
    # A route request may naturally contain “怎么逛”; only a question during an
    # already active collection is handed back to the normal RAG router.
    if not start_collection and any(term in user_text for term in QUESTION_TERMS):
        return None
    collection = collection or new_profile_collection(initial_profile, required_fields=required)
    patch, fields, conflict = _extract_patch(
        user_text,
        allow_bare_detail=True,
        current_field=collection.next_missing_field,
    )
    if conflict:
        return ProfileCollectionResult("clarification", collection, conflict, {}, "conflicting_profile_values")

    # “都可以” resolves only the field that is currently being asked for;
    # it never guesses interests or applies defaults to unrelated fields.
    if not patch and any(term in user_text for term in (*NEUTRAL_TERMS, *SKIP_TERMS)):
        missing = collection.next_missing_field
        if missing:
            patch = {missing: _neutral_value(missing)}
            fields = {missing}

    try:
        profile = update_visitor_profile(collection.profile, **patch) if patch else collection.profile
    except VisitorProfileError as exc:
        return ProfileCollectionResult("clarification", collection, f"{exc} 请重新说明。", {}, "invalid_profile_value")

    resolved = tuple(field for field in COLLECTION_FIELD_ORDER if field in set(collection.resolved_fields).union(fields))
    next_field = next((field for field in collection.required_fields if field not in resolved), None)
    updated = ProfileCollection(
        profile, resolved, "ready" if next_field is None else "collecting",
        required_fields=collection.required_fields,
    )
    if next_field:
        return ProfileCollectionResult("collecting", updated, _prompt(next_field), patch, "profile_field_missing")
    return ProfileCollectionResult(
        "ready",
        updated,
        "已记录您的导览偏好："
        f"{profile.available_minutes} 分钟，"
        f"兴趣：{'、'.join(profile.interests) if profile.interests else '无特别偏好'}，"
        f"讲解深度：{profile.detail_level}。"
        + (
            " 路线偏好：在已审核候选中优先减少预计步行。"
            if profile.route_constraint == "minimize_walking"
            else ""
        ),
        patch,
        "profile_ready",
    )
