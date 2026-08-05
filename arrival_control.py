"""Shared, non-executing recognition for visitor arrival-shaped language.

This module has no node-resolution or state-writing authority.  It only keeps
the lexical boundary used by A1 parsing and semantic-candidate validation in
one place, so a word such as ``看到`` cannot become an arrival because it
contains the character ``到``.
"""

from __future__ import annotations

import re


_BARE_ARRIVAL_FORMS = frozenset(
    {
        "到了", "到啦", "到咯", "我到了", "我到啦", "我到咯",
        "我已到了", "我已经到了", "我到这了", "我到这儿了",
        "到达", "我到下一个点位了", "我到下一站了", "我已到下一个点位了",
    }
)
_EXPLICIT_ARRIVAL = re.compile(
    r"(?:我|我们)(?:\s*人)?(?:\s*自己)?(?:\s*(?:已|已经|刚|终于))?"
    r"(?:\s*(?:走|逛|晃悠))?\s*"
    r"(?:抵达|到达|来到|走到|走进|到位|到了|到啦|到咯|"
    r"到[^，。！？?\s]{0,16}(?:了|啦|咯))"
)
_COMPLETION_ARRIVAL = re.compile(
    r"(?:已|已经|刚|终于)\s*(?:走|逛|晃悠)?\s*"
    r"(?:抵达|到达|来到|走到|走进|到位|到了|到啦|到咯|"
    r"到[^，。！？?\s]{1,16}(?:了|啦|咯)?)"
)
_CURRENT_LOCATION_REPORT = re.compile(
    r"^(?:我现在在|现在人在|现在人就在)\s*[^？?。！!]+$"
)
_STATIC_LOCATION_QUESTION = re.compile(
    r"^(?:(?:我|我们)(?:现在)?在)?[^，。！？?]{0,24}"
    r"(?:能看到|看到|有什么|有哪些|讲讲|介绍|特点|故事|为什么).*[？?]?$"
)
_TEMPORAL_KNOWLEDGE = re.compile(
    r"(?:抵达|到达|来到|走到|走进).{0,12}(?:以后|之后|后).{0,16}"
    r"(?:什么|为什么|有哪些|能看到|介绍|讲讲|特点|故事)"
)
_HYPOTHETICAL_OR_VERIFICATION = re.compile(
    r"(?:如果|是不是|算).{0,12}(?:抵达|到达|来到|走到|走进|到了|到啦|到咯|到)"
)
_NEGATED_OR_IN_TRANSIT = re.compile(
    r"(?:我|我们|朋友|孩子|导游).{0,12}(?:"
    r"还在路上|正在去|还在去|快到|快走到|马上到|"
    r"还没(?:到|抵达|到达|来到|走到)|"
    r"没有(?:到|抵达|到达|来到|走到)|"
    r"尚未(?:到|抵达|到达|来到))"
)
_THIRD_PARTY = re.compile(
    r"(?:朋友|孩子|导游).{0,12}(?:抵达|到达|来到|走到|走进|到了|到啦|到咯|到位|到)"
)
_DESTINATION = re.compile(
    r"(?:想去|想要去|要去|准备去|打算去|接下来去(?!哪|哪儿|哪里)|准备前往|带我到)"
)


def is_safe_arrival_report_text(user_text: str) -> bool:
    """Return whether raw text is a single, first-person arrival report."""
    text = str(user_text or "").strip()
    compact = text.rstrip("。！!？?")
    if not text or "？" in text or "?" in text:
        return False
    if _STATIC_LOCATION_QUESTION.match(text) or _TEMPORAL_KNOWLEDGE.search(text):
        return False
    if _NEGATED_OR_IN_TRANSIT.search(text) or _DESTINATION.search(text):
        return False
    if _HYPOTHETICAL_OR_VERIFICATION.search(text) or _THIRD_PARTY.search(text):
        return False
    if any(term in text for term in ("跳过", "再详细", "详细讲", "把时间改", "结束路线", "结束游览", "顺便", "再讲")):
        return False
    return bool(
        compact in _BARE_ARRIVAL_FORMS
        or _CURRENT_LOCATION_REPORT.match(compact)
        or _EXPLICIT_ARRIVAL.search(text)
        or _COMPLETION_ARRIVAL.search(text)
    )


def looks_like_arrival_control(user_text: str) -> bool:
    """Return whether text is location-control-shaped and must not use RAG.

    This is intentionally broader than ``is_safe_arrival_report_text``: a
    negated, in-transit, hypothetical, or third-party report still needs a
    deterministic clarification.  It deliberately never matches a bare
    ``到`` character.
    """
    text = str(user_text or "").strip()
    compact = text.rstrip("。！!？?")
    if not text or _STATIC_LOCATION_QUESTION.match(text) or _TEMPORAL_KNOWLEDGE.search(text):
        return False
    return bool(
        compact in _BARE_ARRIVAL_FORMS
        or _CURRENT_LOCATION_REPORT.match(compact)
        or _EXPLICIT_ARRIVAL.search(text)
        or _COMPLETION_ARRIVAL.search(text)
        or _HYPOTHETICAL_OR_VERIFICATION.search(text)
        or _NEGATED_OR_IN_TRANSIT.search(text)
        or _THIRD_PARTY.search(text)
        or _DESTINATION.search(text)
    )
