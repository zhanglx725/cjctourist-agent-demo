"""Pure, immutable visitor-preference contract for the C-stage guide flow.

This module intentionally has no dependency on AgentState, TourState, routes
or StopProgram.  C2/C3/C4 will decide when a validated profile is copied into
a live tour; C1 only represents what the visitor has explicitly expressed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from typing import Any, Iterable


DEFAULT_AVAILABLE_MINUTES = 60
DEFAULT_DETAIL_LEVEL = "standard"
DEFAULT_AUDIENCE_MODE = "standard"
DEFAULT_KNOWLEDGE_LEVEL = "general"
DEFAULT_EXPLANATION_STYLE = "standard"
DEFAULT_INTERACTION_MODE = "normal"
MIN_AVAILABLE_MINUTES = 20
MAX_AVAILABLE_MINUTES = 120
VALID_DETAIL_LEVELS = frozenset({"short", "standard", "deep"})
VALID_AUDIENCE_MODES = frozenset({"standard", "child_friendly", "family", "study", "mixed_group"})
VALID_KNOWLEDGE_LEVELS = frozenset({"general", "enthusiast", "professional"})
VALID_EXPLANATION_STYLES = frozenset({
    "standard", "story", "technical", "interactive", "expert",
    "neutral", "child", "family", "student_research", "professional",
    "listen_only", "mixed_group", "dominant_ceo", "cute_junior",
    "ancient_scholar", "warm_sister", "bestie_chat", "buddy_guide",
    "exploration_game", "photo_guide", "hostel_scholar",
    "xiguan_young_master", "cantonese_storyteller",
})
VALID_INTERACTION_MODES = frozenset({"listen_only", "normal", "interactive_tasks"})
VALID_ROUTE_CONSTRAINTS = frozenset({"minimize_walking"})
FUTURE_OPTIONAL_FIELDS = frozenset(
    {"language", "photo_preference", "accessibility_need"}
)
OPTIONAL_ROUTE_FIELDS = frozenset({"route_constraint"})
ACTIVE_FIELDS = frozenset({"available_minutes", "interests", "detail_level"})
# C2 deliberately continues to collect only ACTIVE_FIELDS.  C5 adds a
# separate, explicit-confirmation contract rather than silently making four
# more questions mandatory before a route can start.
C5_PREFERENCE_FIELDS = frozenset(
    {"audience_mode", "knowledge_level", "explanation_style", "interaction_mode"}
)
ALL_FIELDS = (
    ACTIVE_FIELDS
    | C5_PREFERENCE_FIELDS
    | FUTURE_OPTIONAL_FIELDS
    | OPTIONAL_ROUTE_FIELDS
)
LEGACY_IGNORED_FIELDS = frozenset({"visitor_type"})


class VisitorProfileError(ValueError):
    """Raised when explicitly supplied visitor preferences are invalid."""


def normalize_interests(interests: Iterable[str] | str | None) -> tuple[str, ...]:
    """Trim, de-duplicate and stably order explicit interest labels.

    C1 treats labels as stated preferences, not inferred user traits.  Stable
    ordering makes serializations and later deterministic planners repeatable.
    """
    if interests is None:
        return ()
    if isinstance(interests, str):
        raw_items = [interests]
    else:
        try:
            raw_items = list(interests)
        except TypeError as exc:
            raise VisitorProfileError("interests 必须是字符串列表。") from exc
    normalized: dict[str, str] = {}
    for value in raw_items:
        if not isinstance(value, str):
            raise VisitorProfileError("interests 必须是字符串列表。")
        item = value.strip()
        if not item:
            continue
        normalized.setdefault(item.casefold(), item)
    return tuple(normalized[key] for key in sorted(normalized))


def _normalize_minutes(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VisitorProfileError("available_minutes 必须是整数分钟。")
    if not MIN_AVAILABLE_MINUTES <= value <= MAX_AVAILABLE_MINUTES:
        raise VisitorProfileError(
            f"available_minutes 必须介于 {MIN_AVAILABLE_MINUTES} 和 {MAX_AVAILABLE_MINUTES} 分钟之间。"
        )
    return value


def _normalize_detail_level(value: Any) -> str:
    if not isinstance(value, str):
        raise VisitorProfileError("detail_level 必须是 short、standard 或 deep。")
    normalized = value.strip().lower()
    if normalized not in VALID_DETAIL_LEVELS:
        raise VisitorProfileError("detail_level 必须是 short、standard 或 deep。")
    return normalized


def _normalize_enum(name: str, value: Any, allowed: frozenset[str]) -> str:
    choices = "、".join(sorted(allowed))
    if not isinstance(value, str):
        raise VisitorProfileError(f"{name} 必须是：{choices}。")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise VisitorProfileError(f"{name} 必须是：{choices}。")
    return normalized


def _normalize_optional_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise VisitorProfileError(f"{name} 必须是非空字符串或 None。")
    return value.strip().lower() if name == "language" else value.strip()


def _normalize_optional_flag(name: str, value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise VisitorProfileError(f"{name} 必须是布尔值或 None。")
    return value


def _normalize_optional_route_constraint(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VisitorProfileError(
            "route_constraint 必须是 minimize_walking 或 None。"
        )
    normalized = value.strip().lower()
    if normalized not in VALID_ROUTE_CONSTRAINTS:
        raise VisitorProfileError(
            "route_constraint 必须是 minimize_walking 或 None。"
        )
    return normalized


@dataclass(frozen=True)
class VisitorProfile:
    """Validated current-session preference record.

    C5 defaults are neutral values rather than inferred personal traits.  The
    remaining optional interfaces are omitted unless explicitly supplied, and
    no current planner or narrator reads C5 fields until C6/C7.
    """

    available_minutes: int = DEFAULT_AVAILABLE_MINUTES
    interests: tuple[str, ...] = ()
    detail_level: str = DEFAULT_DETAIL_LEVEL
    # C5 values describe this visit's requested guidance experience.  They
    # are never inferred from wording, age, occupation, relationship or other
    # personal attributes, and C5 does not yet feed route/narration logic.
    audience_mode: str = DEFAULT_AUDIENCE_MODE
    knowledge_level: str = DEFAULT_KNOWLEDGE_LEVEL
    explanation_style: str = DEFAULT_EXPLANATION_STYLE
    interaction_mode: str = DEFAULT_INTERACTION_MODE
    language: str | None = None
    photo_preference: bool | None = None
    accessibility_need: bool | None = None
    # Optional, explicit route preference.  It is not a required C2 question
    # and does not imply accessibility, physical ability or an absolute
    # shortest-path guarantee.
    route_constraint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_minutes", _normalize_minutes(self.available_minutes))
        object.__setattr__(self, "interests", normalize_interests(self.interests))
        object.__setattr__(self, "detail_level", _normalize_detail_level(self.detail_level))
        object.__setattr__(self, "audience_mode", _normalize_enum("audience_mode", self.audience_mode, VALID_AUDIENCE_MODES))
        object.__setattr__(self, "knowledge_level", _normalize_enum("knowledge_level", self.knowledge_level, VALID_KNOWLEDGE_LEVELS))
        object.__setattr__(self, "explanation_style", _normalize_enum("explanation_style", self.explanation_style, VALID_EXPLANATION_STYLES))
        object.__setattr__(self, "interaction_mode", _normalize_enum("interaction_mode", self.interaction_mode, VALID_INTERACTION_MODES))
        object.__setattr__(self, "language", _normalize_optional_text("language", self.language))
        object.__setattr__(self, "photo_preference", _normalize_optional_flag("photo_preference", self.photo_preference))
        object.__setattr__(self, "accessibility_need", _normalize_optional_flag("accessibility_need", self.accessibility_need))
        object.__setattr__(
            self,
            "route_constraint",
            _normalize_optional_route_constraint(self.route_constraint),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize active fields and only explicitly present future fields."""
        value = asdict(self)
        value["interests"] = list(self.interests)
        return {key: value[key] for key in (
            "available_minutes", "interests", "detail_level",
            "audience_mode", "knowledge_level", "explanation_style", "interaction_mode",
            "language", "photo_preference", "accessibility_need",
            "route_constraint",
        ) if value[key] is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_visitor_profile(**values: Any) -> VisitorProfile:
    """Create a profile from explicitly provided supported fields only."""
    unknown = set(values).difference(ALL_FIELDS)
    if unknown:
        raise VisitorProfileError(f"不支持的画像字段：{', '.join(sorted(unknown))}")
    return VisitorProfile(**values)


def update_visitor_profile(profile: VisitorProfile, **changes: Any) -> VisitorProfile:
    """Return a new validated profile without mutating the caller's record."""
    if not isinstance(profile, VisitorProfile):
        raise VisitorProfileError("profile 必须是 VisitorProfile。")
    unknown = set(changes).difference(ALL_FIELDS)
    if unknown:
        raise VisitorProfileError(f"不支持的画像字段：{', '.join(sorted(unknown))}")
    return replace(profile, **changes)


def profile_from_dict(values: dict[str, Any]) -> VisitorProfile:
    """Deserialize through the same strict validation path."""
    if not isinstance(values, dict):
        raise VisitorProfileError("画像数据必须是对象。")
    # `visitor_type` was an ambiguous pre-C5 placeholder.  Legacy snapshots
    # may contain it, but it is intentionally discarded rather than mapped to
    # a sensitive or inferred C5 mode.
    sanitized = {key: value for key, value in values.items() if key not in LEGACY_IGNORED_FIELDS}
    return create_visitor_profile(**sanitized)
