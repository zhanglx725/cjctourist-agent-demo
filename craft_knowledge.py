"""Deterministic access to the seven reviewed ornament-craft sections.

Generic questions about a named craft are a closed-domain lookup.  They should
not depend on vector-search ranking, the current tour position, or an LLM tool
decision.  This module reads the existing Markdown knowledge source directly;
it does not duplicate or extend any of its facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from rag_ingestion import DOCUMENT_SOURCES


CRAFT_TERMS = ("陶塑", "灰塑", "木雕", "石雕", "砖雕", "铜铁铸", "彩绘")
CRAFT_DOCUMENT = "07_ornament_crafts.md"
CRAFT_KNOWLEDGE_FILE = (
    Path(__file__).resolve().parent
    / "data"
    / "chen_clan_academy"
    / "knowledge"
    / CRAFT_DOCUMENT
)

BRIEF_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "陶塑": ("工艺性质", "制作与视觉处理"),
    "灰塑": ("工艺性质与位置", "材料与流程"),
    "木雕": ("工艺地位", "主要技法与内容"),
    "石雕": ("工艺特点", "材料与功能"),
    "砖雕": ("工艺性质", "材料与技法"),
    "铜铁铸": ("工艺地位", "陈家祠应用"),
    "彩绘": ("门神", "壁画", "楹联"),
}
LOCATION_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "陶塑": ("工艺性质", "陈家祠应用"),
    "灰塑": ("工艺性质与位置",),
    "木雕": ("使用部位", "代表性空间"),
    "石雕": ("陈家祠应用", "月台亮点"),
    "砖雕": ("陈家祠代表作", "建筑分布与题材"),
    "铜铁铸": ("陈家祠应用",),
    "彩绘": ("门神", "壁画", "楹联"),
}

_DETAIL_MARKERS = (
    "详细讲讲",
    "详细讲解",
    "详细介绍",
    "深入讲讲",
    "展开讲讲",
    "多讲一点",
    "完整介绍",
    "全面介绍",
)
_BRIEF_PATTERNS = (
    r"{craft}(?:工艺)?是什么",
    r"什么是(?:陈家祠(?:的)?)?{craft}(?:工艺)?",
    r"(?:简单|简要)?(?:介绍|讲讲|说说|讲一下)(?:一下)?(?:陈家祠(?:的)?)?{craft}(?:工艺)?",
    r"(?:陈家祠(?:的)?)?{craft}(?:工艺)?是怎么做的",
    r"(?:陈家祠(?:的)?)?{craft}(?:工艺)?有什么(?:工艺)?(?:特点|特征)",
)
_LEADING_POLITENESS = re.compile(r"^(?:请给我|请你|请|能否|可以|麻烦)?")
_TRAILING_PUNCTUATION = re.compile(r"[\s，,。！？!?；;：:“”\"'（）()]+")
_HEADING_PATTERN = re.compile(r"^##\s+([^：:\n]+)\s*[：:]\s*(.+?)\s*$")
_FIELD_PATTERN = re.compile(r"^-\s+\*\*([^*]+)\*\*\s*[：:]\s*(.*)$")


class CraftKnowledgeError(RuntimeError):
    """Raised when the reviewed craft source cannot be parsed safely."""


@dataclass(frozen=True)
class CraftField:
    label: str
    text: str


@dataclass(frozen=True)
class CraftRecord:
    craft: str
    title: str
    fields: tuple[CraftField, ...]
    document: str
    source_ids: tuple[str, ...]

    def as_evidence(self) -> dict[str, object]:
        content = " ".join(
            f"- **{field.label}**：{field.text}" for field in self.fields
        )
        return {
            "document": self.document,
            "title_path": ["陈家祠建筑装饰工艺总览", self.title],
            "source_ids": list(self.source_ids),
            "content": content,
            "craft": self.craft,
            "craft_fields": [
                {"label": field.label, "text": field.text} for field in self.fields
            ],
            "retrieval_methods": ["canonical_craft_section"],
        }


@dataclass(frozen=True)
class CraftExplanationRequest:
    craft: str
    detail_level: Literal["brief", "detailed"]


@dataclass(frozen=True)
class CraftLocationRequest:
    crafts: tuple[str, ...]


@dataclass(frozen=True)
class CraftLocationAnswer:
    message: str
    evidence: tuple[dict[str, object], ...]
    missing_crafts: tuple[str, ...]


def _compact_request(text: str) -> str:
    compact = _TRAILING_PUNCTUATION.sub("", str(text or ""))
    return _LEADING_POLITENESS.sub("", compact)


def parse_craft_explanation_request(
    text: str,
) -> CraftExplanationRequest | None:
    """Recognize a bounded generic craft explanation request.

    Two named crafts indicate a comparison, not a craft definition.  Concrete
    story, object, and location questions deliberately do not match the
    anchored patterns below and remain owned by their existing handlers.
    """
    compact = _compact_request(text)
    named = tuple(craft for craft in CRAFT_TERMS if craft in compact)
    if len(named) != 1:
        return None
    craft = named[0]
    escaped = re.escape(craft)

    for marker in _DETAIL_MARKERS:
        patterns = (
            rf"{re.escape(marker)}(?:一下)?(?:陈家祠(?:的)?)?{escaped}(?:工艺)?",
            rf"(?:陈家祠(?:的)?)?{escaped}(?:工艺)?{re.escape(marker)}(?:一下)?",
        )
        if any(re.fullmatch(pattern, compact) for pattern in patterns):
            return CraftExplanationRequest(craft, "detailed")

    if any(
        re.fullmatch(pattern.format(craft=escaped), compact)
        for pattern in _BRIEF_PATTERNS
    ):
        return CraftExplanationRequest(craft, "brief")
    return None


def parse_craft_location_request(text: str) -> CraftLocationRequest | None:
    """Recognize an explicit multi-craft request for observation locations."""

    compact = _compact_request(text)
    named = tuple(
        sorted(
            (craft for craft in CRAFT_TERMS if craft in compact),
            key=compact.index,
        )
    )
    if len(named) < 2:
        return None
    if any(
        token in compact
        for token in ("区别", "相比", "比较", "不同", "异同", "相对于")
    ):
        return None
    if not any(
        token in compact
        for token in (
            "在哪里",
            "在哪儿",
            "在哪",
            "哪里看",
            "哪儿看",
            "何处",
            "位置",
            "哪些部位",
            "什么部位",
            "什么地方",
            "哪些地方",
            "哪里有",
            "哪儿有",
            "哪里能看到",
            "哪能看到",
            "分布",
            "怎么找",
            "重点留意哪里",
            "重点看哪里",
            "留意哪里",
            "看哪里",
        )
    ):
        return None
    return CraftLocationRequest(crafts=named)


def _parse_craft_source(path: Path) -> dict[str, CraftRecord]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CraftKnowledgeError(f"工艺知识源不可读取：{exc}") from exc

    raw_sections: dict[str, tuple[str, list[CraftField]]] = {}
    current_craft: str | None = None
    current_title = ""
    current_fields: list[CraftField] = []

    def finish_section() -> None:
        nonlocal current_craft, current_title, current_fields
        if current_craft is None:
            return
        if current_craft in raw_sections:
            raise CraftKnowledgeError(f"工艺知识源存在重复标题：{current_craft}")
        if not current_fields:
            raise CraftKnowledgeError(f"工艺知识源缺少字段：{current_craft}")
        raw_sections[current_craft] = (
            current_title,
            list(current_fields),
        )
        current_craft = None
        current_title = ""
        current_fields = []

    for line in lines:
        heading = _HEADING_PATTERN.match(line)
        if heading:
            finish_section()
            candidate = heading.group(1).strip()
            if candidate in CRAFT_TERMS:
                current_craft = candidate
                current_title = f"{candidate}：{heading.group(2).strip()}"
            continue
        if line.startswith("## "):
            finish_section()
            continue
        if current_craft is None:
            continue
        field = _FIELD_PATTERN.match(line)
        if field:
            label = field.group(1).strip()
            value = field.group(2).strip()
            if not label or not value:
                raise CraftKnowledgeError(
                    f"工艺知识源字段不完整：{current_craft}"
                )
            if any(existing.label == label for existing in current_fields):
                raise CraftKnowledgeError(
                    f"工艺知识源字段重复：{current_craft}/{label}"
                )
            current_fields.append(CraftField(label, value))
        elif line.strip() and current_fields:
            previous = current_fields[-1]
            current_fields[-1] = CraftField(
                previous.label, f"{previous.text} {line.strip()}"
            )
    finish_section()

    missing = [craft for craft in CRAFT_TERMS if craft not in raw_sections]
    if missing:
        raise CraftKnowledgeError(
            f"工艺知识源缺少受控条目：{'、'.join(missing)}"
        )

    source_ids = tuple(DOCUMENT_SOURCES.get(CRAFT_DOCUMENT, ()))
    if not source_ids:
        raise CraftKnowledgeError("工艺知识源缺少来源登记")
    return {
        craft: CraftRecord(
            craft=craft,
            title=title,
            fields=tuple(fields),
            document=CRAFT_DOCUMENT,
            source_ids=source_ids,
        )
        for craft, (title, fields) in raw_sections.items()
    }


@lru_cache(maxsize=4)
def _load_craft_records(path_text: str) -> dict[str, CraftRecord]:
    return _parse_craft_source(Path(path_text))


def load_craft_record(
    craft: str, path: Path = CRAFT_KNOWLEDGE_FILE
) -> CraftRecord:
    if craft not in CRAFT_TERMS:
        raise CraftKnowledgeError(f"不受支持的工艺名称：{craft}")
    records = _load_craft_records(str(path.resolve()))
    try:
        return records[craft]
    except KeyError as exc:
        raise CraftKnowledgeError(f"工艺知识源缺少条目：{craft}") from exc


def brief_fields(record: CraftRecord) -> tuple[CraftField, ...]:
    labels = BRIEF_FIELD_LABELS[record.craft]
    by_label = {field.label: field for field in record.fields}
    missing = [label for label in labels if label not in by_label]
    if missing:
        raise CraftKnowledgeError(
            f"简要讲解字段缺失：{record.craft}/{'、'.join(missing)}"
        )
    return tuple(by_label[label] for label in labels)


def location_fields(record: CraftRecord) -> tuple[CraftField, ...]:
    """Select only reviewed fields that answer where a craft can be observed."""

    labels = LOCATION_FIELD_LABELS[record.craft]
    by_label = {field.label: field for field in record.fields}
    missing = [label for label in labels if label not in by_label]
    if missing:
        raise CraftKnowledgeError(
            f"位置说明字段缺失：{record.craft}/{'、'.join(missing)}"
        )
    return tuple(by_label[label] for label in labels)


def render_craft_location_answer(
    request: CraftLocationRequest,
) -> CraftLocationAnswer:
    """Render a bounded list without exposing raw chunks or retrieval metadata."""

    lines = ["可以按下面这些位置寻找："]
    evidence: list[dict[str, object]] = []
    missing: list[str] = []
    for craft in request.crafts:
        try:
            record = load_craft_record(craft)
            fields = location_fields(record)
        except CraftKnowledgeError:
            missing.append(craft)
            lines.append(f"- {craft}：现有审核资料不足以确认观察位置。")
            continue
        statement = "；".join(field.text.rstrip("。") for field in fields) + "。"
        lines.append(f"- {craft}：{statement}")
        evidence.append(
            {
                "document": record.document,
                "title_path": ["陈家祠建筑装饰工艺总览", record.title],
                "source_ids": list(record.source_ids),
                "content": " ".join(field.text for field in fields),
                "craft": craft,
                "craft_fields": [
                    {"label": field.label, "text": field.text}
                    for field in fields
                ],
                "retrieval_methods": ["canonical_craft_location_fields"],
            }
        )
    lines.append(
        "这些是馆方工艺资料中的稳定位置线索；具体区域是否开放、"
        "构件是否清晰可见，请以现场标识和工作人员安排为准。"
    )
    return CraftLocationAnswer(
        message="\n".join(lines),
        evidence=tuple(evidence),
        missing_crafts=tuple(missing),
    )


def _connector(label: str, index: int) -> str:
    if index == 0:
        return ""
    if any(token in label for token in ("材料", "制作", "技法", "施彩")):
        return "在材料与制作上，"
    if any(token in label for token in ("陈家祠", "代表性空间", "月台")):
        return "在陈家祠中，"
    if any(token in label for token in ("题材", "文化", "艺术价值")):
        return "在题材和文化表达上，"
    if any(token in label for token in ("发展", "地域")):
        return "从发展与地域背景看，"
    return "此外，"


def render_craft_explanation(
    record: CraftRecord, detail_level: Literal["brief", "detailed"]
) -> str:
    fields = brief_fields(record) if detail_level == "brief" else record.fields
    paragraphs = [
        f"{_connector(field.label, index)}{field.text.rstrip('。')}。"
        for index, field in enumerate(fields)
    ]
    if detail_level == "detailed":
        labels = {field.label for field in record.fields}
        if record.craft == "彩绘":
            scope = "门神、壁画和楹联"
        elif any(
            any(token in label for token in ("材料", "制作", "技法", "施彩"))
            for label in labels
        ):
            scope = "工艺特点、材料制作和在陈家祠中的呈现"
        else:
            scope = "工艺地位、陈家祠中的应用和题材意义"
        intro = f"关于“{record.craft}”，可以从{scope}完整来看。"
        body = "\n\n".join(paragraphs)
        message = f"{intro}\n\n{body}"
    else:
        message = "\n\n".join(paragraphs)
    # Provenance belongs to the structured evidence channel.  Do not expose
    # internal source identifiers in the visitor-facing craft explanation.
    return message
