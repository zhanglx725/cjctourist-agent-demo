"""Safe presentation model for the request-only photo hint dialog."""

from __future__ import annotations

import re
from dataclasses import dataclass


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])\s*|\n+")


@dataclass(frozen=True)
class PhotoHintCard:
    title: str
    recommended_position: str
    composition: str
    pose: str
    architecture: str
    conditions: str
    safety: str


def _first_matching(sentences: list[str], markers: tuple[str, ...], fallback: str) -> str:
    return next(
        (sentence for sentence in sentences if any(marker in sentence for marker in markers)),
        fallback,
    )


def _best_matching(sentences: list[str], markers: tuple[str, ...], fallback: str) -> str:
    """Prefer the sentence carrying the most relevant reviewed details."""
    ranked = [
        (sum(marker in sentence for marker in markers), index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    score, _, sentence = max(ranked, default=(0, 0, fallback), key=lambda item: (item[0], -item[1]))
    return sentence if score else fallback


def build_photo_hint_card(text: str) -> PhotoHintCard:
    """Classify reviewed prose into fixed UI fields without inventing advice."""
    cleaned = str(text or "").strip()
    if not cleaned:
        fallback = "当前点位暂时没有经核验的具体建议，请以现场开放范围和馆方指引为准。"
        return PhotoHintCard("当前点位", fallback, fallback, fallback, fallback, fallback, fallback)

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    has_title_prefix = bool(re.match(r"^(?:拍摄小提示|【打卡姿势建议】)", lines[0]))
    title = (
        re.sub(r"^(?:拍摄小提示|【打卡姿势建议】)[:：]?\s*", "", lines[0]).strip()
        if has_title_prefix else "当前点位拍照建议"
    )
    body_lines = lines[1:] if has_title_prefix else lines
    sentences = [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split("\n".join(body_lines))
        if sentence.strip()
    ]
    unavailable = "现有资料未提供这一项具体建议，请以现场可见范围为准。"
    return PhotoHintCard(
        title=title or "当前点位",
        recommended_position=_first_matching(
            sentences, ("位置", "机位", "站在", "停留", "取景"), unavailable,
        ),
        composition=_first_matching(
            sentences, ("构图", "背景", "前景", "中轴", "画面", "取景"), unavailable,
        ),
        pose=_best_matching(
            sentences, ("站立", "侧身", "正视", "姿势", "人物", "望向"), unavailable,
        ),
        architecture=_first_matching(
            sentences, ("建筑", "门厅", "屋脊", "山墙", "庭院", "栏板", "构件"), unavailable,
        ),
        conditions=_first_matching(
            sentences, ("光线", "客流", "开放", "现场", "通行"),
            "光线、客流和开放情况请以现场为准。",
        ),
        safety=_first_matching(
            sentences, ("不得", "不要", "严禁", "禁止", "触摸", "攀", "馆方"),
            "请勿触摸、倚靠或攀坐文物，现场规则以馆方指引为准。",
        ),
    )
