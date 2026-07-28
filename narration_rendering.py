"""E5-A3 neutral deterministic rendering of structured guidance evidence.

The renderer has no state-writing dependency.  It accepts only a reviewed
StopProgram, A2's typed evidence bundle and the already-audited GuidancePolicy
snapshot, then returns prose plus candidates that a later A4 node may commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from guidance_evidence_bundle import CoverageCandidate, EvidencePacket, GuidanceEvidenceBundle
from guidance_policy import GuidancePolicy
from guide_program_planner import StopProgram


CRAFT_DIMENSIONS = {
    "definition": ("是", "又称", "工艺性质"),
    "material_or_making": ("材料", "石灰", "泥", "纤维", "塑形", "煅烧", "加工"),
    "technique": ("技法", "堆塑", "雕刻", "刻", "凿", "磨", "镂", "浮雕"),
    "architectural_location": ("屋脊", "门额", "山墙", "屋檐", "栏杆", "建筑", "部位", "常见于"),
    "visual_feature": ("造型", "色彩", "层次", "通透", "繁缛", "视觉", "立体"),
}
ORNAMENT_SHAPE_MARKERS = ("形", "造型", "构图", "描绘", "表现", "全身", "独角", "姿态", "组合", "图中")
ORNAMENT_THEME_MARKERS = ("寓意", "象征", "故事", "传说", "题材", "人物", "祈盼", "辟邪", "保平安", "文化")


@dataclass(frozen=True)
class NarrationRenderResult:
    visitor_message: str
    rendered_craft_ids: tuple[str, ...]
    rendered_ornament_ids: tuple[str, ...]
    used_source_ids: tuple[str, ...]
    eligible_coverage_candidates: tuple[CoverageCandidate, ...]
    content_budget_seconds: int
    allocated_content_seconds: int
    omitted_ornament_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "visitor_message": self.visitor_message,
            "rendered_craft_ids": list(self.rendered_craft_ids),
            "rendered_ornament_ids": list(self.rendered_ornament_ids),
            "used_source_ids": list(self.used_source_ids),
            "eligible_coverage_candidates": [candidate.to_dict() for candidate in self.eligible_coverage_candidates],
            "content_budget_seconds": self.content_budget_seconds,
            "allocated_content_seconds": self.allocated_content_seconds,
            "omitted_ornament_ids": list(self.omitted_ornament_ids),
            "warnings": list(self.warnings),
        }


def _sentences(packet: EvidencePacket) -> list[tuple[str, tuple[str, ...]]]:
    values: list[tuple[str, tuple[str, ...]]] = []
    for entry in packet.evidence:
        text = " ".join(str(entry.get("content", "")).split())
        source_ids = tuple(source for source in entry.get("source_ids", ()) if isinstance(source, str) and source)
        normalized = text.replace("！", "。").replace("？", "。").replace("；", "。")
        for sentence in (part.strip() for part in normalized.split("。")):
            if sentence:
                values.append((sentence + "。", source_ids))
    return values


def _categories(sentence: str, rules: Mapping[str, tuple[str, ...]]) -> set[str]:
    return {name for name, markers in rules.items() if any(marker in sentence for marker in markers)}


def _first_matching(
    sentences: Iterable[tuple[str, tuple[str, ...]]], markers: tuple[str, ...], used: set[str]
) -> tuple[str, tuple[str, ...]] | None:
    for sentence, source_ids in sentences:
        if sentence not in used and any(marker in sentence for marker in markers):
            used.add(sentence)
            return sentence, source_ids
    return None


def _policy_from_program(program: StopProgram) -> GuidancePolicy | None:
    if not program.guidance_policy:
        return None
    try:
        return GuidancePolicy(**program.guidance_policy)
    except TypeError:
        return None


def _render_limit(program: StopProgram, policy: GuidancePolicy | None) -> int:
    max_items = policy.max_items_per_stop if policy else len(program.selected_items)
    # A first craft introduction is folded into the first core item's existing
    # allocation.  Under 150 seconds, only that stable core prefix is rendered.
    budget_limit = 1 if program.budget_seconds < 150 else len(program.selected_items)
    return min(max_items, budget_limit, len(program.selected_items))


def _craft_segment(craft: str, packet: EvidencePacket) -> tuple[list[str], tuple[str, ...], bool, str | None]:
    sentences = _sentences(packet)
    used: set[str] = set()
    selected: list[tuple[str, tuple[str, ...]]] = []
    covered_dimensions: set[str] = set()
    for sentence, source_ids in sentences:
        dimensions = _categories(sentence, CRAFT_DIMENSIONS)
        if dimensions and (not selected or not dimensions.issubset(covered_dimensions)):
            selected.append((sentence, source_ids))
            used.add(sentence)
            covered_dimensions.update(dimensions)
        if len(covered_dimensions) >= 2 and len(selected) >= 1:
            break
    if not selected:
        return [], (), False, f"{craft}缺少可用于首次介绍的工艺证据"
    lines = [f"先认识{craft}：{selected[0][0]}"]
    lines.extend(sentence for sentence, _ in selected[1:])
    lines.append(f"在本点可把视线放在{craft}对象的造型、细部和所在构件上。")
    source_ids = tuple(sorted({source for _, values in selected for source in values}))
    complete = len(covered_dimensions) >= 2
    warning = None if complete else f"{craft}工艺证据暂不足两类信息，未作为完整首次介绍"
    return lines, source_ids, complete, warning


def _ornament_segment(
    item: Any,
    packet: EvidencePacket,
    location: Any,
    *,
    first: bool,
) -> tuple[list[str], tuple[str, ...], bool, str | None]:
    sentences = _sentences(packet)
    used: set[str] = set()
    shape = _first_matching(sentences, ORNAMENT_SHAPE_MARKERS, used)
    theme = _first_matching(sentences, ORNAMENT_THEME_MARKERS, used)
    fallback = next(((sentence, source_ids) for sentence, source_ids in sentences if sentence not in used), None)
    chosen = [value for value in (shape, theme) if value]
    if not chosen and fallback:
        chosen.append(fallback)
    lines = [f"{item.name}是一件{item.craft}装饰。"]
    if getattr(location, "valid", False) and location.raw_location:
        lines.append(f"可先看向{location.raw_location}。")
    else:
        lines.append("可先在本点的相关构件上寻找它的造型细节。")
    lines.extend(sentence for sentence, _ in chosen)
    lines.append(f"观察时，可留意{item.name}的轮廓、细部与周围构件的关系。")
    source_ids = tuple(sorted({source for _, values in chosen for source in values}))
    complete = bool(shape and theme and source_ids)
    if first and not complete:
        warning = f"{item.name}的证据不足以完成首次文物介绍，未列为可提交覆盖候选"
    else:
        warning = None
    if not first and chosen:
        lines.insert(1, "这一处可作为前面内容的简短回顾，再留意它本点的细部。")
    return lines, source_ids, complete if first else False, warning


def render_guidance_evidence(
    program: StopProgram,
    bundle: GuidanceEvidenceBundle,
    guidance_policy: GuidancePolicy | dict[str, Any] | None = None,
) -> NarrationRenderResult:
    """Render only evidence supplied by E5-A2; never write session state."""
    if bundle.node_id != program.node_id:
        raise ValueError("GuidanceEvidenceBundle node_id must match StopProgram node_id")
    policy = guidance_policy if isinstance(guidance_policy, GuidancePolicy) else _policy_from_program(program)
    if isinstance(guidance_policy, dict):
        policy = GuidancePolicy(**guidance_policy)
    limit = _render_limit(program, policy)
    rendered_items = program.selected_items[:limit]
    omitted = tuple(item.ornament_id for item in program.selected_items[limit:])
    lines = [f"现在来到{program.display_name}。"]
    rendered_crafts: list[str] = []
    rendered_ornaments: list[str] = []
    used_sources: set[str] = set()
    warnings: list[str] = []
    eligible: list[CoverageCandidate] = []
    eligible_by_subject = {(candidate.subject_kind, candidate.subject_id): candidate for candidate in bundle.coverage_candidates}

    crafts_in_prefix = tuple(dict.fromkeys(item.craft for item in rendered_items))
    for craft in crafts_in_prefix:
        status = bundle.coverage_status["craft"].get(craft)
        if status == "first_introduction":
            packet = bundle.craft_overviews.get(craft)
            if packet and packet.evidence:
                segment, sources, complete, warning = _craft_segment(craft, packet)
                lines.extend(segment)
                used_sources.update(sources)
                if complete and (candidate := eligible_by_subject.get(("craft", craft))):
                    eligible.append(candidate)
                    rendered_crafts.append(craft)
                if warning:
                    warnings.append(warning)
            else:
                warnings.append(f"{craft}没有合格的工艺总述证据")
        elif status == "repeat":
            lines.append(f"{craft}在本次游览中已经介绍过；这里转而看当前对象的新细部。")

    for item in rendered_items:
        packet = bundle.ornament_details.get(item.ornament_id)
        if not packet or not packet.evidence:
            warnings.append(f"{item.name}没有合格的单件文物证据")
            continue
        first = bundle.coverage_status["ornament"].get(item.ornament_id) == "first_introduction"
        segment, sources, complete, warning = _ornament_segment(
            item, packet, bundle.location_evidence.get(item.ornament_id), first=first
        )
        lines.extend(segment)
        rendered_ornaments.append(item.ornament_id)
        used_sources.update(sources)
        if complete and (candidate := eligible_by_subject.get(("ornament", item.ornament_id))):
            eligible.append(candidate)
        if warning:
            warnings.append(warning)

    if len(rendered_ornaments) >= 2:
        first, second = rendered_items[0], rendered_items[1]
        if first.craft == second.craft:
            lines.append(f"这两件都属于{first.craft}，可以对照它们各自的造型处理。")
        else:
            lines.append("也可以留意两种工艺在构件处理上的不同。")
    if omitted:
        warnings.append("本站预算优先保留核心对象，后续对象留待需要时再展开")
    if policy and policy.interaction_mode != "listen_only" and policy.interaction_task_enabled:
        lines.append("您可以留意其中一处造型细部；无需回答也不影响继续导览。")
    if used_sources:
        lines.append(f"来源：{'、'.join(sorted(used_sources))}。")
    lines.append("讲解结束后，您可确认是否完成本点参观。")
    allocated = sum(item.planned_seconds for item in rendered_items)
    return NarrationRenderResult(
        visitor_message="\n".join(lines),
        rendered_craft_ids=tuple(rendered_crafts),
        rendered_ornament_ids=tuple(rendered_ornaments),
        used_source_ids=tuple(sorted(used_sources)),
        eligible_coverage_candidates=tuple(eligible),
        content_budget_seconds=program.budget_seconds,
        allocated_content_seconds=allocated,
        omitted_ornament_ids=omitted,
        warnings=tuple(warnings),
    )
