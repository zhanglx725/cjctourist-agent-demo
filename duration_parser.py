"""Deterministic visit-duration parsing shared by route and tour flows.

This module only recognizes explicit duration expressions.  Callers decide
whether their surrounding route/profile/update context permits using a parsed
value; the parser never invokes an LLM and never changes state.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


_CHINESE_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
    "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_DURATION_RE = re.compile(
    r"(?:"
    r"(?P<ninety>(?:一个半小时|一小时半|1\.5\s*小时))"
    r"|(?P<half>半小时)"
    r"|(?P<quarter>一刻钟)"
    r"|(?P<three_quarters>三刻钟)"
    # The numeric-minute form must not restart at the fractional tail of an
    # unsupported expression such as "1.5分钟" and silently parse it as 5 分钟.
    r"|(?P<minutes>(?<![.\d])(?:\d{1,3}|[零〇一二三四五六七八九十两]+)\s*分钟)"
    # Common English minute units are accepted only with an explicit integer.
    # The ASCII-letter boundary prevents a partial match inside unrelated text
    # such as "30minimum" while still allowing Chinese text to follow the unit
    # directly, as in "30min路线".
    r"|(?P<english_minutes>(?<![.\d])\d{1,3}\s*(?:minutes?|mins?)(?![A-Za-z]))"
    r"|(?P<hours>(?:(?:\d{1,3}(?:\.\d+)?)\s*个?|一个|[零〇一二三四五六七八九十两]+)\s*小时)"
    r")",
    flags=re.IGNORECASE,
)

ROUTE_CONTEXT_TERMS = (
    "路线", "规划", "怎么逛", "游览", "参观顺序", "导览", "带我逛",
)
_REMAINING_CONTEXT_RE = re.compile(r"(?:只剩|还剩|剩余|把(?:游览)?时间改成|时间改成|改为|改成)")


@dataclass(frozen=True)
class DurationParseResult:
    minutes: int | None
    reason_code: str
    matched_expressions: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.minutes is not None and self.reason_code == "parsed"


def _parse_chinese_number(value: str) -> int | None:
    """Parse the small Chinese numeral range used by the supported durations."""
    if not value or any(char not in {*_CHINESE_DIGITS, "十"} for char in value):
        return None
    if "十" not in value:
        if len(value) == 1:
            return _CHINESE_DIGITS[value]
        return None
    if value.count("十") != 1:
        return None
    left, right = value.split("十", 1)
    if len(left) > 1 or len(right) > 1:
        return None
    tens = 1 if not left else _CHINESE_DIGITS.get(left)
    ones = 0 if not right else _CHINESE_DIGITS.get(right)
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


def _number_value(value: str) -> Decimal | None:
    """Return an exact numeric value for supported duration units."""
    normalized = value.strip().replace("个", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d+)?", normalized):
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
    parsed = _parse_chinese_number(normalized)
    return Decimal(parsed) if parsed is not None else None


def _candidate_minutes(match: re.Match[str]) -> int | None:
    if match.group("ninety"):
        return 90
    if match.group("half"):
        return 30
    if match.group("quarter"):
        return 15
    if match.group("three_quarters"):
        return 45
    minutes = match.group("minutes")
    if minutes:
        value = minutes.removesuffix("分钟").strip()
        numeric = _number_value(value)
        return int(numeric) if numeric is not None and numeric == numeric.to_integral_value() else None
    english_minutes = match.group("english_minutes")
    if english_minutes:
        value = re.sub(
            r"\s*(?:minutes?|mins?)\s*$",
            "",
            english_minutes,
            flags=re.IGNORECASE,
        )
        numeric = _number_value(value)
        return int(numeric) if numeric is not None and numeric == numeric.to_integral_value() else None
    hours = match.group("hours")
    if hours:
        value = hours.removesuffix("小时").strip()
        numeric = _number_value(value)
        if numeric is None:
            return None
        duration = numeric * Decimal(60)
        return int(duration) if duration == duration.to_integral_value() else None
    return None


def parse_duration_minutes(text: str) -> DurationParseResult:
    """Parse one unambiguous explicit duration into integer minutes.

    ``15`` and other values outside a caller's product limits are still parsed.
    VisitorProfile/route validation remains responsible for rejecting values
    that the active route policy cannot serve.
    """
    # "\u4e24\u4e2a\u5c0f\u65f6" and "\u4e24\u5c0f\u65f6" are the same supported duration.
    # This is an input normalisation, not a separate parsing path.
    text = text.replace("\u4e24\u4e2a\u5c0f\u65f6", "\u4e24\u5c0f\u65f6")
    candidates: list[tuple[int, str]] = []
    for match in _DURATION_RE.finditer(text):
        minutes = _candidate_minutes(match)
        if minutes is not None:
            candidates.append((minutes, match.group(0)))
    if not candidates:
        return DurationParseResult(None, "no_duration")
    values = {minutes for minutes, _ in candidates}
    expressions = tuple(expression for _, expression in candidates)
    if len(values) != 1:
        return DurationParseResult(None, "ambiguous_duration", expressions)
    return DurationParseResult(next(iter(values)), "parsed", expressions)


def has_route_duration_context(text: str) -> bool:
    """Return whether explicit duration appears in a route-start context."""
    parsed = parse_duration_minutes(text)
    if not parsed.ok:
        return False
    return any(term in text for term in ROUTE_CONTEXT_TERMS) or any(
        phrase in text for phrase in ("我有", "我只有", "我仅有", "可用时间")
    )


def has_remaining_duration_context(text: str) -> bool:
    """Return whether explicit duration is framed as a remaining-time update."""
    parsed = parse_duration_minutes(text)
    return parsed.reason_code in {"parsed", "ambiguous_duration"} and bool(_REMAINING_CONTEXT_RE.search(text))
