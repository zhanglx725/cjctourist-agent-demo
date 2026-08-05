"""Deterministic P4-03 title and original blessing policy."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


POLICY_VERSION = "post_visit_award_policy_v1"


class PostVisitAwardError(ValueError):
    pass


def is_post_visit_request(text: str) -> bool:
    compact = "".join(str(text or "").split()).rstrip("。！!？?")
    return any(term in compact for term in (
        "称号", "祝福", "游览总结", "参观总结", "看看总结", "查看总结",
    ))


def build_post_visit_award(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, dict) or summary.get("schema_version") != "visit_summary_v1":
        raise PostVisitAwardError("游览总结不可用。")
    basis = summary.get("title_basis")
    if not isinstance(basis, dict):
        raise PostVisitAwardError("称号依据不可用。")
    question_count = basis.get("question_count")
    question_count = question_count if isinstance(question_count, int) and question_count >= 0 else None
    matched = tuple(item for item in basis.get("matched_interest_ids") or [] if isinstance(item, str) and item)
    crafts = tuple(item for item in basis.get("introduced_craft_ids") or [] if isinstance(item, str) and item)
    topics = tuple(item for item in basis.get("introduced_topic_names") or [] if isinstance(item, str) and item)
    diversity = basis.get("content_diversity_count")
    diversity = diversity if isinstance(diversity, int) and diversity >= 0 else 0
    style = basis.get("explanation_style")
    completed = basis.get("completion_kind") == "completed_all_stops"
    visited = basis.get("visited_stop_count")
    visited = visited if isinstance(visited, int) and visited >= 0 else 0

    if question_count is not None and question_count >= 3:
        title_id, title = "curious_explorer", "好奇探索家"
        reason = f"本次游览中提出了 {question_count} 次问题。"
        blessing = "愿这份认真追问的好奇心，继续带你发现建筑与工艺里的细节。"
    elif len(matched) >= 2:
        title_id, title = "interest_connoisseur", "岭南知艺人"
        reason = "实际讲解覆盖了多项你明确关注的内容：" + "、".join(matched) + "。"
        blessing = "愿今天遇见的工艺细节，成为你继续认识岭南文化的一扇窗。"
    elif diversity >= 5:
        title_id, title = "many_arts_wanderer", "百艺巡游者"
        reason = f"本次成功讲解覆盖了 {diversity} 类工艺与题材信号。"
        blessing = "愿不同工艺与题材留下的印象，在离开后仍能慢慢展开。"
    elif style == "story" and len(topics) >= 2:
        title_id, title = "story_tracer", "故事寻踪者"
        reason = "选择了故事风格，并实际听到了多项审核题材。"
        blessing = "愿今天听见的故事，陪你把建筑上的人物与纹样记得更久。"
    elif completed and visited >= 2:
        title_id, title = "route_finisher", "陈家祠行旅完成者"
        reason = f"按本轮记录完成了全部路线，共确认参观 {visited} 个讲解点。"
        blessing = "愿这段完整行程为你留下一份从整体到细节的岭南记忆。"
    else:
        title_id, title = "mindful_visitor", "陈家祠漫游者"
        reason = "依据本轮可审计的实际参观记录授予中性纪念称号。"
        blessing = "愿今天的一段驻足，为你留下轻松而清晰的文化记忆。"
    return {
        "schema_version": "post_visit_award_v1",
        "policy_version": POLICY_VERSION,
        "title_id": title_id,
        "title": title,
        "reason": reason,
        "blessing": blessing,
        "disclaimer": "这是本次游览的趣味纪念称号，不是官方认证或游客评级。",
        "basis_snapshot": deepcopy(basis),
    }
