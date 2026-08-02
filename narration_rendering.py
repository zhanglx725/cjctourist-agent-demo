"""E5-A3 neutral deterministic rendering of structured guidance evidence.

The renderer has no state-writing dependency.  It accepts only a reviewed
StopProgram, A2's typed evidence bundle and the already-audited GuidancePolicy
snapshot, then returns prose plus candidates that a later A4 node may commit.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

from guidance_evidence_bundle import CoverageCandidate, EvidencePacket, GuidanceEvidenceBundle
from guidance_policy import GuidancePolicy
from guide_program_planner import StopProgram
from narration_style_policy import NarrationStylePolicy, STYLE_SCHEMA_VERSION, compile_narration_style
from ornament_detail_runtime import build_object_evidence_view, render_object_detail


CRAFT_DIMENSIONS = {
    "definition": ("是", "又称", "工艺性质"),
    "material_or_making": ("材料", "石灰", "泥", "纤维", "塑形", "煅烧", "加工"),
    "technique": ("技法", "堆塑", "雕刻", "刻", "凿", "磨", "镂", "浮雕"),
    "architectural_location": ("屋脊", "门额", "山墙", "屋檐", "栏杆", "建筑", "部位", "常见于"),
    "visual_feature": ("造型", "色彩", "层次", "通透", "繁缛", "视觉", "立体"),
}
ORNAMENT_SHAPE_MARKERS = ("形", "造型", "构图", "描绘", "表现", "全身", "独角", "姿态", "组合", "图中")
ORNAMENT_THEME_MARKERS = ("寓意", "象征", "故事", "传说", "题材", "人物", "祈盼", "辟邪", "保平安", "文化")
ORNAMENT_STORY_ORIGIN_MARKERS = ("故事", "传说", "源自", "取材", "相传")
ORNAMENT_STORY_DETAIL_MARKERS = ("画面", "图中", "描绘", "刻画", "表现", "场面", "雕饰", "冒着")


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
    style_id: str
    style_schema_version: str
    style_fallback_used: bool
    style_warning_codes: tuple[str, ...]

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
            "style_id": self.style_id,
            "style_schema_version": self.style_schema_version,
            "style_fallback_used": self.style_fallback_used,
            "style_warning_codes": list(self.style_warning_codes),
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


def _story_context(
    sentences: list[tuple[str, tuple[str, ...]]],
    theme: tuple[str, tuple[str, ...]] | None,
    used: set[str],
) -> tuple[str, tuple[str, ...]] | None:
    """Keep one later, object-level story detail after an audited origin.

    A source sentence such as “取材于《三国演义》” identifies a theme but
    does not itself explain the depicted episode.  When the same accepted
    object packet contains a following sentence, it can be rendered as the
    minimal context detail.  The helper never looks outside that packet and
    does not manufacture a detail when the source stops at a title.
    """
    if theme is None or not any(marker in theme[0] for marker in ORNAMENT_STORY_ORIGIN_MARKERS):
        return None
    try:
        theme_index = next(index for index, entry in enumerate(sentences) if entry == theme)
    except StopIteration:
        return None
    later = [entry for entry in sentences[theme_index + 1:] if entry[0] not in used]
    for sentence, source_ids in later:
        if any(marker in sentence for marker in ORNAMENT_STORY_DETAIL_MARKERS):
            used.add(sentence)
            return sentence, source_ids
    if later:
        sentence, source_ids = later[0]
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


def _resolve_style(policy: GuidancePolicy | None) -> tuple[NarrationStylePolicy | None, str, bool, tuple[str, ...]]:
    """Load only a policy-selected style; renderer-neutral is the fail-closed fallback."""
    if policy is None:
        return None, "neutral", True, ("style_policy_unavailable",)
    try:
        style = compile_narration_style(policy)
        return style, style.style_id, False, ()
    except Exception:
        # Do not let an unavailable/malformed style package suppress factual
        # guidance.  None means retain A3's original neutral phrasing.
        return None, "neutral", True, ("style_library_unavailable",)


def _style_frame(style_id: str) -> str | None:
    """Non-factual, deterministic framing controlled by approved style metadata."""
    frames = {
        "child": "我们用简单的办法，一步步看看这里的装饰。",
        "family": "可以一起留意这些构件的造型和细节。",
        "student_research": "可把工艺、构图与下列证据分开观察。",
        "professional": "以下按工艺、构图与题材信息组织观察。",
        "listen_only": "下面为连续讲解。",
        "mixed_group": "先看容易观察的要点；如需可再展开术语。",
    }
    return frames.get(style_id)


def _style_observation(style_id: str, visible_detail: str) -> str:
    prompts = {
        "child": f"可以试着找一找{visible_detail}。",
        "family": f"可以一起留意{visible_detail}。",
        "student_research": f"可把{visible_detail}作为观察线索。",
        "professional": f"可核对{visible_detail}的处理方式。",
        "mixed_group": f"先留意{visible_detail}；需要时可再深入。",
    }
    return prompts.get(style_id, f"观察时，可留意{visible_detail}。")


def _ornament_observation(
    style_id: str,
    item: Any,
    location: Any,
    shape: tuple[str, tuple[str, ...]] | None,
) -> str | None:
    """Give one object-specific cue without inventing a visual detail.

    A reviewed raw location is the preferred cue because it distinguishes
    objects at the same stop without asking the renderer to infer features.
    When that mapping is unavailable, a returned shape sentence may serve as
    the cue.  With neither, the caller must omit a prompt rather than fall
    back to a generic "surrounding components" sentence.
    """
    if getattr(location, "valid", False) and location.raw_location:
        detail = f"{location.raw_location}处的{item.name}"
        if style_id == "listen_only":
            return f"本件的观察位置是{detail}。"
        verbs = {
            "child": "可以先找一找",
            "family": "可以一起留意",
            "student_research": "可将",
            "professional": "可核对",
            "mixed_group": "先留意",
        }
        verb = verbs.get(style_id, "可先看向")
        suffix = "作为观察线索" if style_id == "student_research" else ""
        return f"{verb}{detail}{suffix}。"
    if shape:
        sentence = shape[0]
        if style_id == "listen_only":
            return f"本件可观察的造型线索是：{sentence}"
        return f"可将这条造型信息作为观察线索：{sentence}"
    return None


def _template(style: NarrationStylePolicy | None, key: str, slots: dict[str, str]) -> str | None:
    if style is None or style.style_id == "neutral":
        return None
    try:
        value = style.templates[key].format(**slots).strip()
    except (KeyError, ValueError, AttributeError):
        return None
    return value or None


def _definition_slot(craft: str, sentence: str) -> str:
    normalized = sentence.strip().rstrip("。")
    for prefix in (f"{craft}是一种", f"{craft}是", f"{craft}又称"):
        if normalized.startswith(prefix):
            remainder = normalized[len(prefix):].strip("，、 ")
            if remainder:
                return remainder
    return normalized


_RAW_LIST_PREFIX = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_RAW_BOLD_LABEL_PREFIX = re.compile(r"^\*\*[^*]+\*\*\s*[：:]\s*")


def _visitor_craft_sentence(sentence: str) -> str:
    """Remove source Markdown labels while preserving the reviewed fact.

    Craft packets originate in a field-labelled Markdown source.  Those labels
    are useful for retrieval and audit, but visitor narration must not expose
    the source's list marker or field formatting as if it were a guide script.
    """
    cleaned = _RAW_LIST_PREFIX.sub("", sentence.strip())
    return _RAW_BOLD_LABEL_PREFIX.sub("", cleaned).strip()


def _craft_segment(
    craft: str, packet: EvidencePacket, style: NarrationStylePolicy | None, style_id: str
) -> tuple[list[str], tuple[str, ...], bool, str | None]:
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
    visitor_selected = [(_visitor_craft_sentence(sentence), source_ids) for sentence, source_ids in selected]
    template_line = _template(style, "first_craft_intro_style", {
        "craft_name": craft,
        "craft_definition": _definition_slot(craft, visitor_selected[0][0]),
        "object_name": "", "observation_location": "", "visible_detail": "", "evidence_fact": "",
    })
    lines = [template_line or f"先认识{craft}：{visitor_selected[0][0]}"]
    lines.extend(sentence for sentence, _ in visitor_selected[1:])
    lines.append(_style_observation(style_id, f"{craft}对象的造型、细部和所在构件"))
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
    style: NarrationStylePolicy | None,
    style_id: str,
) -> tuple[list[str], tuple[str, ...], bool, str | None]:
    raw_location = location.raw_location if getattr(location, "valid", False) else None
    view = build_object_evidence_view(
        ornament_id=item.ornament_id,
        name=item.name,
        craft=item.craft,
        node_id=getattr(location, "node_id", ""),
        raw_location=raw_location,
        evidence=packet.evidence,
    )
    rendered = render_object_detail(
        view,
        first=first,
        detailed=False,
        listen_only=style_id == "listen_only",
    )
    lines = list(rendered.paragraphs)
    source_ids = rendered.source_ids
    complete = bool(
        view.coverage_level == "full"
        and view.raw_location
        and source_ids
        and (view.visual_sentences or view.story_sentences)
    )
    if first and not complete:
        warning = f"{item.name}的证据不足以完成首次文物介绍，未列为可提交覆盖候选"
    else:
        warning = None
    if not first and source_ids:
        lines.insert(1, "这一处作为前面内容的简短回顾，再补充本点可核对的细部。")
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
    style, style_id, style_fallback_used, style_warning_codes = _resolve_style(policy)
    limit = _render_limit(program, policy)
    rendered_items = program.selected_items[:limit]
    omitted = tuple(item.ornament_id for item in program.selected_items[limit:])
    lines = [f"现在来到{program.display_name}。"]
    if frame := _style_frame(style_id):
        lines.append(frame)
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
                segment, sources, complete, warning = _craft_segment(craft, packet, style, style_id)
                # Use a plain-text section label instead of Markdown list
                # syntax.  Studio renders wrapped list items with a deep
                # hanging indent on narrow screens.
                lines.append(f"【工艺背景：{craft}】")
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
            item, packet, bundle.location_evidence.get(item.ornament_id), first=first, style=style, style_id=style_id
        )
        # Keep every reviewed object in its own flat section.  In particular,
        # never prefix these paragraphs with '-' or '*' because a wrapped
        # visitor sentence then becomes a nested-looking hanging indent.
        lines.append(f"【观察对象：{item.name}】")
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
        lines.append("【观察提示】")
        lines.append("您可以留意其中一处造型细部；无需回答也不影响继续导览。")
    # The completion instruction is deliberately a peer section, rather than
    # the last line of an object or observation section.
    lines.append("【下一步】")
    lines.append("讲解结束后，您可确认是否完成本点参观。")
    allocated = sum(item.planned_seconds for item in rendered_items)
    return NarrationRenderResult(
        visitor_message="\n\n".join(lines),
        rendered_craft_ids=tuple(rendered_crafts),
        rendered_ornament_ids=tuple(rendered_ornaments),
        used_source_ids=tuple(sorted(used_sources)),
        eligible_coverage_candidates=tuple(eligible),
        content_budget_seconds=program.budget_seconds,
        allocated_content_seconds=allocated,
        omitted_ornament_ids=omitted,
        warnings=tuple(warnings),
        style_id=style_id,
        style_schema_version=STYLE_SCHEMA_VERSION,
        style_fallback_used=style_fallback_used,
        style_warning_codes=style_warning_codes,
    )
