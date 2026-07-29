"""Deterministic visitor-safety answers sourced from the reviewed knowledge file.

The Markdown knowledge file remains the only fact source.  This module only
selects and rephrases its reviewed ``禁止事项`` bullets; it does not infer
live conditions, permissions, or new museum rules.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any


SAFETY_SOURCE_FILE = Path(
    "data/chen_clan_academy/knowledge/03_visit_services.md"
)

SAFETY_QUERY_CUES: dict[str, tuple[str, ...]] = {
    "smoking": ("吸烟", "抽烟", "点烟"),
    "touching": (
        "触摸",
        "摸一下",
        "摸文物",
        "摸展品",
        "碰文物",
        "碰展品",
        "触碰",
    ),
    "flash": ("闪光灯", "开闪光", "用闪光"),
    "commercial_photo": ("商业拍摄", "商业摄影", "商拍"),
    "drone": ("无人机", "航拍", "飞行器"),
    "food": (
        "带食物",
        "带饮料",
        "吃东西",
        "喝饮料",
        "奶茶",
        "零食",
        "含糖饮料",
    ),
}

SAFETY_RULE_MARKERS: dict[str, tuple[str, ...]] = {
    "smoking": ("吸烟",),
    "touching": ("触摸",),
    "flash": ("闪光灯",),
    "commercial_photo": ("商业拍摄",),
    "drone": ("无人机航拍", "全域禁飞"),
    "food": ("含糖饮料", "食物进入展厅"),
}


class VisitSafetyRuleError(RuntimeError):
    """Raised when the reviewed safety section cannot be loaded safely."""


def _plain_markdown(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\s*-\s*", "", text)
    text = text.replace("**", "")
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def load_visit_safety_rules() -> dict[str, str]:
    """Load the five reviewed prohibition bullets and fail closed on drift."""
    try:
        lines = SAFETY_SOURCE_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise VisitSafetyRuleError("无法读取审核安全规则。") from exc

    in_safety = False
    in_prohibitions = False
    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "## 安全与参观规则":
            in_safety = True
            continue
        if in_safety and stripped.startswith("## "):
            break
        if not in_safety:
            continue
        if stripped == "- **禁止事项**：":
            in_prohibitions = True
            continue
        if in_prohibitions and stripped.startswith("- **高峰期提示**"):
            break
        if in_prohibitions and line.startswith("  - "):
            bullets.append(_plain_markdown(stripped))

    rules: dict[str, str] = {}
    for rule_id, markers in SAFETY_RULE_MARKERS.items():
        matches = [
            bullet for bullet in bullets
            if any(marker in bullet for marker in markers)
        ]
        if len(matches) != 1:
            raise VisitSafetyRuleError(
                f"安全规则 {rule_id} 未唯一匹配审核资料。"
            )
        rules[rule_id] = matches[0]
    return rules


def matched_visit_safety_rule_ids(user_query: str) -> tuple[str, ...]:
    """Return audited rule IDs explicitly requested in this turn."""
    return tuple(
        rule_id
        for rule_id, cues in SAFETY_QUERY_CUES.items()
        if any(cue in user_query for cue in cues)
    )


def is_visit_safety_question(user_query: str) -> bool:
    return bool(matched_visit_safety_rule_ids(user_query))


def answer_visit_safety_question(user_query: str) -> dict[str, Any] | None:
    """Render a concise, conclusion-first answer without exposing internals."""
    rule_ids = matched_visit_safety_rule_ids(user_query)
    if not rule_ids:
        return None
    try:
        rules = load_visit_safety_rules()
    except VisitSafetyRuleError:
        return {
            "message": (
                "我暂时无法核验对应的馆内安全规则。"
                "请遵守现场标识并向工作人员确认后再进行。"
            ),
            "rule_ids": (),
            "verified": False,
        }

    introductions = {
        "smoking": "不可以在陈家祠内吸烟。",
        "touching": "不可以触摸建筑构件或展品。",
        "flash": "室内文物展柜禁止使用闪光灯。",
        "commercial_photo": "未经报备，不可以进行商业拍摄。",
        "drone": "不可以直接使用无人机航拍，景区全域禁飞。",
        "food": "含糖饮料和食物不能带入展厅内部。",
    }
    lines: list[str] = []
    for rule_id in rule_ids:
        lines.append(introductions[rule_id])
        detail = rules[rule_id]
        if detail.rstrip("。") not in introductions[rule_id]:
            lines.append(detail)
    if "food" in rule_ids:
        lines.append("如需饮食，可前往庭院休息区。")
    lines.append("请同时遵守现场标识和工作人员要求。")
    return {
        "message": "\n".join(dict.fromkeys(lines)),
        "rule_ids": rule_ids,
        "verified": True,
    }
