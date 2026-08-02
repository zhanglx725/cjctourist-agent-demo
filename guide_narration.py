"""B3.1 visitor-facing narration from audited StopProgram evidence.

The module deliberately separates internal scheduling/evidence data from the
visitor message.  The deterministic renderer is the default.  An optional
injected narrator may be used later, but it receives only selected reviewed
objects and returned RAG evidence and is rejected when it emits raw evidence
dump markers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from guide_program_planner import StopProgram
from guidance_policy import GuidancePolicy
from ornament_detail_runtime import build_object_evidence_view, render_object_detail


RAW_DUMP_MARKERS = (
    ".md", "source_ids", "title_path", "核心观察", "计划约", "知识块",
    "审核位置", "类型：", "简介：",
)
STORY_ORIGIN_MARKERS = ("故事", "传说", "源自", "取材", "相传")
STORY_DETAIL_MARKERS = ("画面", "图中", "描绘", "刻画", "表现", "场面", "冒着")


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


def _evidence_sentences(content: str) -> list[str]:
    normalized = " ".join(content.split())
    return [part.strip() + "。" for part in normalized.replace("！", "。").replace("？", "。").split("。") if part.strip()]


def _facts_for_item(content: str, *, detailed: bool) -> tuple[str, ...]:
    """Select compact, object-level evidence without inventing a story.

    The ordinary B3 path stays concise.  A deliberate “再讲详细一点” may
    retain an audited story-origin sentence plus one later scene/context
    sentence from the same object evidence.  If the source has no such detail
    this returns only what it actually supplies.
    """
    sentences = _evidence_sentences(content)
    if not sentences:
        return ()
    if not detailed:
        return (sentences[0],)
    origin_index = next(
        (index for index, sentence in enumerate(sentences) if any(marker in sentence for marker in STORY_ORIGIN_MARKERS)),
        None,
    )
    if origin_index is None:
        return (sentences[1] if len(sentences) > 1 else sentences[0],)
    detail_index = next(
        (
            index
            for index in range(origin_index + 1, len(sentences))
            if any(marker in sentences[index] for marker in STORY_DETAIL_MARKERS)
        ),
        origin_index + 1 if origin_index + 1 < len(sentences) else None,
    )
    selected = [sentences[origin_index]]
    if detail_index is not None and sentences[detail_index] != selected[0]:
        selected.append(sentences[detail_index])
    return tuple(selected)


def _source_ids(evidence_by_item: dict[str, list[dict[str, Any]]]) -> tuple[str, ...]:
    return tuple(sorted({source_id for values in evidence_by_item.values() for item in values for source_id in item.get("source_ids", [])}))


def _safe_item_evidence(item: Any, evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep B3's craft fallback, but never borrow another object's story."""
    ornament_entries: list[dict[str, Any]] = []
    craft_entries: list[dict[str, Any]] = []
    for entry in evidence:
        document = Path(str(entry.get("document", ""))).name
        title = " ".join(entry.get("title_path") or [])
        content = str(entry.get("content", ""))
        if document == "08_ornament_items.md" and item.name in title:
            ornament_entries.append(entry)
        elif document == "07_ornament_crafts.md" and (item.craft in title or item.craft in content):
            craft_entries.append(entry)
    return ornament_entries, craft_entries


def _observation_prompt(
    name: str,
    craft: str,
    observation_location: str | None,
    *,
    detailed: bool,
    policy: GuidancePolicy | None,
) -> str:
    target = f"{observation_location}处的{name}" if observation_location else f"{name}的{craft}造型"
    if policy and policy.audience_mode == "child_friendly":
        return f"可以先找一找{target}。"
    if policy and policy.audience_mode == "family":
        return f"大家可以一起留意{target}。"
    if policy and policy.audience_mode == "study":
        return f"可将{target}作为本件的观察线索。"
    if detailed:
        return f"这是一处{craft}装饰，可先辨认{target}。"
    return f"这是一处{craft}装饰，可先看向{target}。"


def _policy_from_program(program: StopProgram) -> GuidancePolicy | None:
    if not program.guidance_policy:
        return None
    try:
        return GuidancePolicy(**program.guidance_policy)
    except TypeError:
        # A malformed audit payload must never lead to invented narration;
        # retain the established neutral deterministic B3 fallback.
        return None


def _opening(program: StopProgram, policy: GuidancePolicy | None, detailed: bool) -> str:
    count = len(program.selected_items)
    if policy is None:
        return f"我们把{program.display_name}再看细一点：" if detailed else f"现在来到{program.display_name}，先抓住{count}个观察重点："
    if policy.audience_mode == "child_friendly":
        return f"现在来到{program.display_name}，我们用简单的观察任务认识这里："
    if policy.audience_mode == "family":
        return f"现在来到{program.display_name}，大家可以一起观察{count}个重点："
    if policy.audience_mode == "study":
        return f"现在来到{program.display_name}，本点先完成以下观察目标："
    if policy.audience_mode == "mixed_group":
        return f"现在来到{program.display_name}，先用通俗方式看{count}个重点："
    if policy.narrative_mode == "story":
        return f"现在来到{program.display_name}，我们从画面与题材的线索进入："
    if policy.narrative_mode in {"technical", "expert"}:
        return f"现在来到{program.display_name}，从工艺与构件关系看{count}个重点："
    return f"我们把{program.display_name}再看细一点：" if detailed else f"现在来到{program.display_name}，先抓住{count}个观察重点："


def _closing(policy: GuidancePolicy | None, detailed: bool) -> str:
    if policy is None and detailed:
        # Preserve B3's established neutral fallback for callers that have
        # not yet supplied a C6 policy.
        return "如果您愿意，可以把刚才看到的细节告诉我；讲解结束后再确认是否完成本点参观。"
    if policy and policy.interaction_task_enabled:
        if policy.audience_mode == "child_friendly":
            return "小任务：在这两处装饰里选一处，说说你先注意到的一个形状或细节。"
        if policy.audience_mode == "family":
            return "可以一起选一处装饰，说说大家先注意到的同一个细节。"
        if policy.audience_mode == "study":
            return "思考任务：比较刚才的造型和周围构件，哪一处细部最能支持你的观察？"
        return "观察任务：选一处刚才提到的装饰，指出最能体现其工艺特点的一个细部。"
    if policy and policy.audience_mode == "mixed_group" and policy.optional_deepening_enabled:
        return "如需更深入的工艺补充，我可以在不改变当前路线的前提下继续展开。"
    if detailed:
        return "讲解结束后，您可确认是否完成本点参观。"
    return "您可先停留观察；需要展开细节可选择“再讲详细一点”。"


def _deterministic_message(
    program: StopProgram,
    evidence_by_item: dict[str, list[dict[str, Any]]],
    *,
    detailed: bool,
) -> str:
    policy = _policy_from_program(program)
    # The program has already applied the C6 item cap plus the reviewed stop
    # budget.  Narration must never silently add a third object.
    items = program.selected_items
    lines = [_opening(program, policy, detailed)]
    for item in items:
        evidence = evidence_by_item.get(item.ornament_id, [])
        ornament_entries, craft_entries = _safe_item_evidence(item, evidence)
        view = build_object_evidence_view(
            ornament_id=item.ornament_id,
            name=item.name,
            craft=item.craft,
            node_id=program.node_id,
            raw_location=item.observation_location,
            evidence=ornament_entries,
        )
        # B3 remains the compatibility path for detail requests and
        # re-expression.  Match E5's flat, non-Markdown hierarchy so Studio
        # cannot turn long object text into hanging list items.
        lines.append(f"【观察对象：{item.name}】")
        if view.source_ids:
            rendered = render_object_detail(
                view,
                first=True,
                detailed=detailed,
                listen_only=bool(policy and policy.interaction_mode == "listen_only"),
            )
            lines.extend(rendered.paragraphs)
        else:
            lines.append(f"{item.name}是一件{item.craft}装饰。这是一处{item.craft}装饰的审核关联对象。")
            if item.observation_location:
                lines.append(f"它与{item.observation_location}存在审核关联；可结合现场标识观察。")
            facts = _facts_for_item(str(craft_entries[0].get("content", "")), detailed=detailed) if craft_entries else ()
            if facts:
                lines.extend(facts)
            lines.append("未检索到可引用的事实资料，因此不据名称扩写题材或故事。")
        if item.comparison_reason:
            lines.append(f"这里特意选它作对照，{item.comparison_reason}。")
    lines.append("【下一步】")
    lines.append(_closing(policy, detailed))
    return "\n\n".join(lines)


def _llm_prompt(program: StopProgram, evidence_by_item: dict[str, list[dict[str, Any]]], detailed: bool) -> str:
    payload = {
        "point": program.display_name,
        "detail": "deep" if detailed else "standard",
        "guidance_policy": program.guidance_policy,
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
