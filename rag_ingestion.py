"""Local Markdown ingestion for the Chen Clan Academy RAG snapshot.

This module deliberately has no embedding or vector-store dependency.  It turns the
curated Markdown corpus into deterministic, inspectable chunks first; the next RAG
step will index these :class:`KnowledgeChunk` objects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable


KNOWLEDGE_DIR = Path("data/chen_clan_academy/knowledge")

# The registry is currently document-level.  Keep this mapping in code until the
# registry is migrated to machine-readable YAML/JSON in a later maintenance step.
DOCUMENT_SOURCES = {
    "01_basic_info.md": ("S01",),
    "02_history_architecture.md": ("S02", "S04", "S06", "S08", "S09"),
    "03_visit_services.md": ("S01", "S03", "S05"),
    "04_events_notices.md": ("S01",),
    "06_ticketing_rules.md": ("S07",),
    "07_ornament_crafts.md": ("S10",),
    "08_ornament_items.md": ("S11",),
    "09_ornament_locations.md": ("S11",),
    "10_people_builders_craftspeople.md": (
        "S02", "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18",
    ),
    "11_architectural_conservation.md": (
        "S09", "S13", "S15", "S16", "S17", "S19", "S20", "S21", "S22", "S23",
        "S24", "S25", "S26", "S27", "S28", "S29",
    ),
}

# Most documents have one source family.  The history document deliberately mixes
# map, historical, layout and conservation sources, so attribution must be made at
# section level rather than attaching every document source to every answer.
SECTION_SOURCES = {
    "02_history_architecture.md": {
        "电子地图读图：建筑布局": ("S06",),
        "历史沿革": ("S02", "S04"),
        "百年历史时间线（馆方资料补充）": ("S08",),
        "建筑格局与参观亮点": ("S04", "S06"),
        "文物保护与科技应用": ("S09",),
        "文化解释": ("S02",),
    },
    "10_people_builders_craftspeople.md": {
        "一、可用于普通导览的人物与群体": ("S02", "S12", "S14"),
        "二、文物保护、研究与工艺传承人物": ("S13", "S15", "S16", "S17"),
        "三、陶塑商号：可讲作营造组织，不等同于个人工匠": ("S10", "S11", "S14"),
        "四、博物馆藏品建设相关人物": ("S18",),
    },
    "11_architectural_conservation.md": {
        "一、保护原则在陈家祠中的可核验实践": ("S13", "S16", "S27"),
        "二、灰塑：现有证据最充分的专项保护材料": ("S13", "S16", "S17", "S22", "S23", "S26"),
        "三、木构件、木雕与白蚁保护": ("S09", "S19", "S20", "S28"),
        "四、青砖墙体、基础和整体结构安全": ("S09", "S15", "S19", "S20", "S24"),
        "五、陶塑、石雕、砖雕和彩绘：已有巡查，专项病害资料不足": ("S19",),
        "六、重要保护与修缮时间线": (
            "S13", "S16", "S17", "S19", "S20", "S21", "S22", "S23", "S24", "S25", "S27", "S29",
        ),
    },
}

DOCUMENT_TYPES = {
    "01_basic_info.md": "basic_info",
    "02_history_architecture.md": "history_architecture",
    "03_visit_services.md": "visit_service",
    "04_events_notices.md": "event_notice",
    "06_ticketing_rules.md": "ticketing_snapshot",
    "07_ornament_crafts.md": "ornament_craft",
    "08_ornament_items.md": "ornament_item",
    "09_ornament_locations.md": "ornament_location",
    # Reuse the reviewed public taxonomy so controlled history/architecture
    # queries can retrieve these extensions without opening a new category.
    "10_people_builders_craftspeople.md": "history_architecture",
    "11_architectural_conservation.md": "history_architecture",
}


@dataclass(frozen=True)
class KnowledgeChunk:
    """A source-grounded unit to be indexed and returned as RAG evidence."""

    chunk_id: str
    content: str
    document: str
    title_path: tuple[str, ...]
    category: str
    source_ids: tuple[str, ...]
    status: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    verified_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_DATE = r"(\d{4}-\d{2}-\d{2})"


def _normalise(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def _metadata(document: str, text: str) -> dict[str, str | None]:
    """Extract explicit snapshot metadata without inventing unavailable values."""
    status = None
    status_match = re.search(r"(?:当前|规则)?状态[：:]\s*([^。\n；;]+)", text)
    if status_match:
        status = status_match.group(1).strip()
    elif document in {"04_events_notices.md", "06_ticketing_rules.md"}:
        status = "snapshot"

    def find(label: str) -> str | None:
        match = re.search(label + r"[：:]\s*" + _DATE, text)
        return match.group(1) if match else None

    verified = find(r"(?:最后核验|核验日期|采集日期|整理日期|数据快照日期)")
    return {
        "status": status,
        "valid_from": find(r"开始日期"),
        "valid_to": find(r"结束日期"),
        "verified_at": verified,
    }


def _source_ids(document: str, titles: list[str]) -> tuple[str, ...]:
    """Return the narrowest registered source set for a knowledge section."""
    return SECTION_SOURCES.get(document, {}).get(titles[-1], DOCUMENT_SOURCES.get(document, ()))


def _make_chunk(document: str, titles: list[str], body: str, index: int) -> KnowledgeChunk | None:
    body = _normalise(body)
    if not body:
        return None
    metadata = _metadata(document, body)
    return KnowledgeChunk(
        chunk_id=f"{document.removesuffix('.md')}:{index:04d}",
        content=body,
        document=document,
        title_path=tuple(titles),
        category=DOCUMENT_TYPES.get(document, "general"),
        source_ids=_source_ids(document, titles),
        **metadata,
    )


def _split_by_h2(document: str, markdown: str) -> Iterable[tuple[list[str], str]]:
    """Split all documents at H2, keeping H3+ content with its parent topic.

    This makes every ornament name (which is H2) and every craft category (also H2)
    a standalone chunk, while retaining explanatory subheadings in their context.
    """
    title = document.removesuffix(".md")
    current_titles = [title]
    body: list[str] = []
    found_h2 = False
    split_h3 = document == "04_events_notices.md"
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == 1:
            title = match.group(2)
            current_titles = [title]
            continue
        if match and len(match.group(1)) == 2:
            if found_h2:
                yield current_titles, "\n".join(body)
            found_h2 = True
            current_titles = [title, match.group(2)]
            body = []
            continue
        # Each dated notice is an independent retrieval unit.  Keeping several
        # notices together would allow one expired notice to contaminate another.
        if match and len(match.group(1)) == 3 and split_h3:
            if body:
                yield current_titles, "\n".join(body)
            current_titles = [*current_titles[:2], match.group(2)]
            body = []
            continue
        body.append(line)
    if found_h2:
        yield current_titles, "\n".join(body)
    else:
        yield current_titles, "\n".join(body)


def chunk_markdown(document: str, markdown: str) -> list[KnowledgeChunk]:
    """Convert one curated knowledge document into stable chunks."""
    chunks: list[KnowledgeChunk] = []
    for index, (titles, body) in enumerate(_split_by_h2(document, markdown), start=1):
        chunk = _make_chunk(document, titles, body, index)
        if chunk:
            chunks.append(chunk)
    return chunks


def load_knowledge_chunks(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[KnowledgeChunk]:
    """Load only curated Markdown under ``knowledge/``; raw/evaluation stay excluded."""
    chunks: list[KnowledgeChunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path.name, path.read_text(encoding="utf-8")))
    return chunks
