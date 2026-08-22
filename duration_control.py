"""Deterministic ownership check for explicit duration control turns."""

from __future__ import annotations

import re

from duration_parser import parse_duration_minutes


_DURATION_TOKEN = re.compile(
    r"(?:\d{1,3}(?:\.\d+)?\s*个?小时|[零〇一二三四五六七八九十两]+\s*个?小时|一个半小时|一小时半|"
    r"\d{1,3}(?:\.\d+)?\s*分钟|[零〇一二三四五六七八九十两]+\s*分钟)"
)
_CONTROL_PREFIXES = ("我有", "我只有", "我仅有", "我还有", "我还剩", "还剩", "剩余", "可用时间")


def classify_duration_control_text(text: str) -> str | None:
    """Return ``parsed``, ``ambiguous`` or ``invalid`` for owned duration turns."""
    raw = str(text or "").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw).rstrip("。！!？?")
    tokens = list(_DURATION_TOKEN.finditer(compact))
    if not tokens:
        return None
    contextual = any(compact.startswith(prefix) for prefix in _CONTROL_PREFIXES)
    bare = len(tokens) == 1 and tokens[0].span() == (0, len(compact))
    if not contextual and not bare:
        return None
    parsed = parse_duration_minutes(raw)
    if parsed.reason_code == "ambiguous_duration":
        return "ambiguous"
    if parsed.reason_code != "parsed":
        return "invalid"
    return "parsed"
