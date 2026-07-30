"""Evidence-only object-detail views shared by narration and point Q&A.

This module deliberately knows no route state, RAG implementation, or visitor
profile.  It accepts only one already-resolved reviewed object plus evidence
blocks, rejects blocks that are not that object's ``08_ornament_items`` entry,
and returns compact visitor-safe paragraphs and internal audit metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ORNAMENT_DOCUMENT = "08_ornament_items.md"
THEME_MARKERS = ("题材", "故事", "传说", "源自", "出自", "取材", "典故", "寓意", "象征")
VISUAL_MARKERS = ("画面", "图中", "描绘", "刻画", "表现", "雕饰", "构图", "全身", "造型", "上方", "中部", "下方", "东边", "西边", "口含", "脚踩", "抱扶")
STORY_ORIGIN_MARKERS = ("故事", "传说", "源自", "出自", "取材", "相传")


def _sentences(content: Any) -> tuple[str, ...]:
    normalized = " ".join(str(content or "").split())
    normalized = normalized.replace("！", "。").replace("？", "。").replace("；", "。")
    return tuple(part.strip() + "。" for part in normalized.split("。") if part.strip())


def _title_parts(entry: Mapping[str, Any]) -> tuple[str, ...]:
    value = entry.get("title_path", ())
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(part.strip() for part in value if isinstance(part, str) and part.strip())


def _source_ids(entry: Mapping[str, Any]) -> tuple[str, ...]:
    raw = entry.get("source_ids", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(source.strip() for source in raw if isinstance(source, str) and source.strip()))


def _is_same_object_entry(entry: Mapping[str, Any], name: str) -> bool:
    if Path(str(entry.get("document", ""))).name != ORNAMENT_DOCUMENT:
        return False
    return name in _title_parts(entry) and bool(_source_ids(entry))


@dataclass(frozen=True)
class ObjectEvidenceView:
    ornament_id: str
    name: str
    craft: str
    node_id: str
    raw_location: str | None
    identity_sentences: tuple[str, ...]
    visual_sentences: tuple[str, ...]
    subject_sentences: tuple[str, ...]
    story_sentences: tuple[str, ...]
    meaning_sentences: tuple[str, ...]
    source_ids: tuple[str, ...]
    coverage_level: str


@dataclass(frozen=True)
class ObjectDetailRender:
    paragraphs: tuple[str, ...]
    source_ids: tuple[str, ...]
    coverage_level: str

    @property
    def visitor_text(self) -> str:
        return "\n\n".join(self.paragraphs)


def build_object_evidence_view(
    *,
    ornament_id: str,
    name: str,
    craft: str,
    node_id: str,
    raw_location: str | None,
    evidence: Iterable[Mapping[str, Any]],
) -> ObjectEvidenceView:
    """Classify only accepted evidence for the resolved audited object."""
    accepted = [entry for entry in evidence if isinstance(entry, Mapping) and _is_same_object_entry(entry, name)]
    sentences = tuple(sentence for entry in accepted for sentence in _sentences(entry.get("content")))
    sources = tuple(sorted({source for entry in accepted for source in _source_ids(entry)}))
    subject = tuple(sentence for sentence in sentences if any(marker in sentence for marker in THEME_MARKERS))
    visual = tuple(sentence for sentence in sentences if any(marker in sentence for marker in VISUAL_MARKERS))
    meaning = tuple(sentence for sentence in sentences if any(marker in sentence for marker in ("寓意", "象征", "祈福", "辟邪", "保平安")))

    origin_index = next(
        (index for index, sentence in enumerate(sentences) if any(marker in sentence for marker in STORY_ORIGIN_MARKERS)),
        None,
    )
    story = sentences[origin_index + 1:] if origin_index is not None else ()
    if story or visual:
        level = "full"
    elif subject or meaning:
        level = "partial"
    elif raw_location or craft:
        level = "basic"
    else:
        level = "insufficient"
    return ObjectEvidenceView(
        ornament_id=ornament_id,
        name=name,
        craft=craft,
        node_id=node_id,
        raw_location=raw_location.strip() if isinstance(raw_location, str) and raw_location.strip() else None,
        identity_sentences=sentences,
        visual_sentences=visual,
        subject_sentences=subject,
        story_sentences=story,
        meaning_sentences=meaning,
        source_ids=sources,
        coverage_level=level,
    )


def _first_distinct(values: Iterable[str], used: set[str]) -> str | None:
    for value in values:
        if value not in used:
            used.add(value)
            return value
    return None


def render_object_detail(
    view: ObjectEvidenceView,
    *,
    first: bool,
    detailed: bool,
    listen_only: bool = False,
) -> ObjectDetailRender:
    """Render only facts in one object view as flat visitor paragraphs."""
    paragraphs = [f"{view.name}是一件{view.craft}装饰。"]
    if view.raw_location:
        paragraphs.append(f"它与{view.raw_location}存在审核关联；可结合现场标识观察。")
    if view.coverage_level == "insufficient":
        paragraphs.append("现有资料不足以安全说明这件对象的具体题材或故事，因此不作推测性补充。")
        return ObjectDetailRender(tuple(paragraphs), (), view.coverage_level)

    used: set[str] = set()
    theme = _first_distinct(view.subject_sentences, used)
    story = _first_distinct(view.story_sentences, used) if first or detailed else None
    # A first introduction must retain one object-level visible/depicted
    # detail when the accepted packet supplies it; otherwise it degenerates
    # into an origin label even though the scene is available.
    visual = _first_distinct(view.visual_sentences, used) if (first or detailed) else None
    meaning = _first_distinct(view.meaning_sentences, used) if detailed else None
    if theme:
        paragraphs.append(theme)
    if story:
        paragraphs.append(story)
    if visual:
        paragraphs.append(visual)
    if meaning:
        paragraphs.append(meaning)
    if not theme and not story and not visual and not meaning:
        paragraphs.append("现有资料目前只足以确认其工艺和审核关联位置，不据此补写题材或故事。")
    if view.raw_location:
        if listen_only:
            paragraphs.append(f"本件可结合{view.raw_location}处的构件位置继续辨认。")
        else:
            paragraphs.append(f"观察时，可结合{view.raw_location}处的构件位置辨认其造型。")
    return ObjectDetailRender(tuple(paragraphs), view.source_ids, view.coverage_level)
