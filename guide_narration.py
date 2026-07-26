"""B3.1 visitor-facing narration from audited StopProgram evidence.

The module deliberately separates internal scheduling/evidence data from the
visitor message.  The deterministic renderer is the default.  An optional
injected narrator may be used later, but it receives only selected reviewed
objects and returned RAG evidence and is rejected when it emits raw evidence
dump markers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from guide_program_planner import StopProgram


RAW_DUMP_MARKERS = (
    ".md", "source_ids", "title_path", "核心观察", "计划约", "知识块",
    "审核位置", "类型：", "简介：",
)


@dataclass(frozen=True)
class GuideNarration:
    visitor_message: str
    source_ids: tuple[str, ...]
    used_llm: bool
    fallback_reason: str | None = None


def _complete_sentence(content: str, index: int = 0) -> str | None:
    """Return a complete, compact sentence; never slice an unfinished chunk."""
    normalized = " ".join(content.split())
    sentences = [part.strip() for part in normalized.replace("！", "。").replace("？", "。").split("。") if part.strip()]
    if index >= len(sentences):
        return None
    sentence = sentences[index]
    return sentence + "。"


def _source_ids(evidence_by_item: dict[str, list[dict[str, Any]]]) -> tuple[str, ...]:
    return tuple(sorted({source_id for values in evidence_by_item.values() for item in values for source_id in item.get("source_ids", [])}))


def _observation_prompt(
    name: str, craft: str, observation_location: str | None, *, detailed: bool
) -> str:
    where = f"在{observation_location}，" if observation_location else ""
    if detailed:
        return f"{where}这是一处{craft}装饰。请把视线停在{name}的造型和细部层次上，再与周围构件作对照。"
    return f"{where}这是一处{craft}装饰。找到{name}后，留意它与周围构件的关系。"


def _deterministic_message(
    program: StopProgram,
    evidence_by_item: dict[str, list[dict[str, Any]]],
    *,
    detailed: bool,
) -> str:
    items = program.selected_items[:2] if not detailed else program.selected_items
    if detailed:
        lines = [f"我们把{program.display_name}再看细一点："]
    else:
        lines = [f"现在来到{program.display_name}，先抓住两个观察重点："]
    for index, item in enumerate(items, start=1):
        evidence = evidence_by_item.get(item.ornament_id, [])
        sentence_index = 1 if detailed else 0
        fact = _complete_sentence(str(evidence[0].get("content", "")), sentence_index) if evidence else None
        if fact is None and evidence:
            fact = _complete_sentence(str(evidence[0].get("content", "")), 0)
        lines.append(
            f"{index}. {item.name}：{_observation_prompt(item.name, item.craft, item.observation_location, detailed=detailed)}"
        )
        if item.comparison_reason:
            lines.append(f"   这里特意选它作对照，{item.comparison_reason}。")
        if fact:
            lines.append(f"   {fact}")
        else:
            lines.append("   当前未检索到可引用的事实资料，不据名称扩写其寓意或故事，我们先以现场观察为主。")
    if detailed:
        lines.append("如果您愿意，可以把刚才看到的细节告诉我；讲解结束后再确认是否完成本点参观。")
    else:
        lines.append("您可先停留观察；需要展开细节可选择“再讲详细一点”。")
    return "\n".join(lines)


def _llm_prompt(program: StopProgram, evidence_by_item: dict[str, list[dict[str, Any]]], detailed: bool) -> str:
    payload = {
        "point": program.display_name,
        "detail": "deep" if detailed else "standard",
        "objects": [
            {
                "name": item.name,
                "craft": item.craft,
                "evidence": [
                    {"content": entry.get("content", ""), "source_ids": entry.get("source_ids", [])}
                    for entry in evidence_by_item.get(item.ornament_id, [])[:1]
                ],
            }
            for item in program.selected_items
        ],
    }
    return (
        "你是现场导游。仅使用以下审核对象和 evidence 生成简洁中文讲解；"
        "不补充外部事实，不展示文件名、原始 chunk、内部角色或时间字段。"
        "没有 evidence 时明确资料不足。\n"
        + repr(payload)
    )


def _acceptable_llm_message(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and not any(marker in normalized for marker in RAW_DUMP_MARKERS)


def compose_guide_narration(
    program: StopProgram,
    evidence_by_item: dict[str, list[dict[str, Any]]],
    *,
    detailed: bool = False,
    narrator: Callable[[str], str] | None = None,
) -> GuideNarration:
    """Compose a visitor message while retaining evidence separately for audit."""
    fallback = _deterministic_message(program, evidence_by_item, detailed=detailed)
    source_ids = _source_ids(evidence_by_item)
    if narrator is None:
        return GuideNarration(fallback, source_ids, used_llm=False)
    try:
        candidate = narrator(_llm_prompt(program, evidence_by_item, detailed))
    except Exception:
        return GuideNarration(fallback, source_ids, used_llm=False, fallback_reason="narrator_unavailable")
    if not _acceptable_llm_message(candidate):
        return GuideNarration(fallback, source_ids, used_llm=False, fallback_reason="narrator_output_rejected")
    return GuideNarration(candidate.strip(), source_ids, used_llm=True)
