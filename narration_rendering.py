"""E5-A3 neutral deterministic rendering of structured guidance evidence.

The renderer has no state-writing dependency.  It accepts only a reviewed
StopProgram, A2's typed evidence bundle and the already-audited GuidancePolicy
snapshot, then returns prose plus candidates that a later A4 node may commit.
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

from guidance_evidence_bundle import CoverageCandidate, EvidencePacket, GuidanceEvidenceBundle, optional_dimension_id
from guidance_policy import GuidancePolicy
from guide_program_planner import StopProgram
from narration_style_policy import NarrationStylePolicy, STYLE_SCHEMA_VERSION, compile_narration_style
from narration_service_tail import COMPLETION_PROMPT
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
OPTIONAL_CONTEXT_SKIP_MARKERS = (
    "不得", "不能", "资料不足", "尚缺", "本轮检索", "证据边界", "导览边界",
    "整理日期", "来源", "核验状态", "是否允许逐字引用", "是否为直接相关",
)


@dataclass(frozen=True)
class NarrationRenderResult:
    visitor_message: str
    rendered_craft_ids: tuple[str, ...]
    rendered_ornament_ids: tuple[str, ...]
    rendered_dimension_ids: tuple[str, ...]
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
    fact_units: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "visitor_message": self.visitor_message,
            "rendered_craft_ids": list(self.rendered_craft_ids),
            "rendered_ornament_ids": list(self.rendered_ornament_ids),
            "rendered_dimension_ids": list(self.rendered_dimension_ids),
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
            "fact_units": [dict(unit) for unit in self.fact_units],
        }


@dataclass(frozen=True)
class StopGuidanceCompatibilityComponents:
    """Reviewed expression-only components available to stop guidance only."""

    opening: str | None


def stop_guidance_compatibility_components(
    style: NarrationStylePolicy | None,
) -> StopGuidanceCompatibilityComponents:
    """Adapt reviewed point components for the stop-guidance compatibility path.

    The source library predates scene contracts and stores the phrases under a
    generic ``opening`` key.  This adapter is the only renderer-facing path
    that may consume it; route opening and arrival confirmation never receive
    these components.  ``next(iter(...))`` preserves the prior stable first
    reviewed choice without coupling callers to array positions.
    """
    if style is None or style.style_id == "neutral":
        return StopGuidanceCompatibilityComponents(opening=None)
    candidates = style.point_narration_components.get("opening", ())
    opening = next(
        (str(candidate).strip() for candidate in candidates if str(candidate).strip()),
        None,
    )
    return StopGuidanceCompatibilityComponents(opening=opening)


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
        "child": "别着急，我们一起慢慢看看，像找宝藏一样发现藏在建筑里的小线索。",
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
        candidates = style.templates[key]
        if isinstance(candidates, tuple):
            seed = "\x1f".join((style.style_id, key, *(f"{name}={slots[name]}" for name in sorted(slots))))
            index = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big") % len(candidates)
            template = candidates[index]
        else:
            template = candidates
        value = template.format(**slots).strip()
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
_INTERNAL_OBJECT_GUIDANCE = (
    "审核关联", "可结合现场标识", "构件位置辨认", "存在审核", "未核验",
)
_AUDIT_LOCATION_STATEMENT = re.compile(
    r"^它与(?P<location>.+?)存在审核关联；可结合现场标识观察。?$"
)
_AUDIT_OBSERVATION_STATEMENT = re.compile(
    r"^观察时，可结合(?P<location>.+?)处的构件位置辨认其造型。?$"
)
_CHILD_STORY_MARKERS = ("传说", "民间故事", "人们说")
_CHILD_CRAFT_NAME = re.compile(r"^([^，。；：]{1,16}?)(?:是|又称)")
_CHILD_STORY_ORIGIN = re.compile(
    r"^(?:这种)?(?P<name>[^，。；]{1,24}?)(?:造型|形象)是根据"
    r"(?P<origin>[^，。；]+?)(?:传说|故事)而来的。?$"
)
_CHILD_STORY_THEME = re.compile(
    r"^(?:这个)?题材源自(?P<origin>[^，。；]+?)(?:，寓意(?P<meaning>[^。]+))?。?$"
)


def _visitor_craft_sentence(sentence: str) -> str:
    """Remove source Markdown labels while preserving the reviewed fact.

    Craft packets originate in a field-labelled Markdown source.  Those labels
    are useful for retrieval and audit, but visitor narration must not expose
    the source's list marker or field formatting as if it were a guide script.
    """
    cleaned = _RAW_LIST_PREFIX.sub("", sentence.strip())
    return _RAW_BOLD_LABEL_PREFIX.sub("", cleaned).strip()


def _visitor_object_statement(statement: str) -> str:
    """Translate retrieval/audit phrasing into a visitor-facing fact sentence.

    The reviewed source sentence remains attached to the fact unit for audit.
    Only the public rendering changes: visitors need a usable location cue,
    never an explanation of the internal evidence relationship.
    """
    cleaned = statement.strip()
    if match := _AUDIT_LOCATION_STATEMENT.match(cleaned):
        return f"它在{match.group('location')}；可以对照现场标识来找。"
    if match := _AUDIT_OBSERVATION_STATEMENT.match(cleaned):
        return f"找它时，先对照{match.group('location')}的位置，再认它的造型。"
    return cleaned


def _child_friendly_fact_statement(
    statement: str,
    *,
    topic_kind: str,
) -> str:
    """Render a reviewed child-safe summary with an auditable source sentence.

    This is deliberately a small, deterministic rewrite vocabulary rather
    than an unconstrained model paraphrase.  It gives the role layer facts a
    child-readable shape while keeping every summary tied one-to-one to the
    reviewed sentence selected below.  The model remains free only to add
    non-factual imagery around these bounded statements.
    """
    source = statement.strip()
    if topic_kind == "craft":
        match = _CHILD_CRAFT_NAME.match(source)
        if match and "装饰" in source:
            name = match.group(1).strip("“”\"")
            alias = re.search(r"民间称[“\"](?P<alias>[^”\"]+)[”\"]", source)
            summary = f"{name}是一门传统装饰手艺。"
            if alias:
                summary += f"人们也叫它“{alias.group('alias')}”。"
            return summary
    if topic_kind == "ornament":
        story = _CHILD_STORY_ORIGIN.match(source)
        if story:
            name = story.group("name").strip()
            origin = story.group("origin").strip("，、 ")
            return f"传说里，{name}的模样来自{origin}传说。"
        theme = _CHILD_STORY_THEME.match(source)
        if theme:
            origin = theme.group("origin").strip("，、 ")
            return f"传说里，这个题材来自{origin}。"
    return source


def _child_role_fact_pairs(
    statements: tuple[str, ...], *, topic_kind: str,
) -> tuple[tuple[str, str], ...]:
    """Select a concise, visitor-safe reviewed subset for child role prose.

    The deterministic fallback keeps the complete rendered evidence. This
    narrower list is only the immutable fact contract supplied to the child
    role layer, so audit wording and a long folklore paragraph do not become
    mandatory child narration merely because they aid the evidence view.
    """
    cleaned = tuple(
        statement.strip()
        for statement in statements
        if statement.strip()
        and not any(marker in statement for marker in _INTERNAL_OBJECT_GUIDANCE)
    )
    if topic_kind == "craft":
        # The normal craft definition often contains a long list of building
        # positions.  Keep one auditable origin sentence and render its
        # deterministic child summary instead of making that list mandatory.
        selected = cleaned[:1]
        return tuple(
            (_child_friendly_fact_statement(statement, topic_kind=topic_kind), statement)
            for statement in selected
        )
    if not cleaned:
        return ()

    identity = cleaned[0]
    details = cleaned[1:]
    story = [
        statement for statement in details
        if any(marker in statement for marker in _CHILD_STORY_MARKERS)
    ]
    visual = [
        statement for statement in details
        if any(marker in statement for marker in ORNAMENT_SHAPE_MARKERS)
    ]
    # A short reviewed story is the most valuable second beat for child
    # narration.  Use a visible detail when no story exists; never force a
    # long object dossier merely to fill the slot.
    candidates = story or visual or list(details)
    selected = min(candidates, key=len) if candidates else None
    selected_statements = (
        (identity, selected)
        if selected and selected != identity else (identity,)
    )
    return tuple(
        (_child_friendly_fact_statement(statement, topic_kind=topic_kind), statement)
        for statement in selected_statements
    )


@dataclass(frozen=True)
class _RoleFactPresentation:
    """One style's public fact text and its reviewed source boundary.

    Every role enters the same content-plan / generation / validation / commit
    path.  Most styles present the reviewed statements verbatim; ``child``
    selects a smaller deterministic, source-traceable presentation.  Keeping
    that distinction in this single value object prevents a child-only
    rendering branch from becoming a second narration architecture.
    """

    statements: tuple[str, ...]
    source_statements: tuple[str, ...]


def _role_fact_presentation(
    statements: tuple[str, ...], *, topic_kind: str, style_id: str,
) -> _RoleFactPresentation:
    """Return the public fact contract for any role style.

    Every public role receives the same small audit-to-visitor normalization;
    raw reviewed wording remains in ``source_statements``.  Child additionally
    selects a concise, deterministic subset.
    """
    source_statements = tuple(statement.strip() for statement in statements if statement.strip())
    if style_id != "child":
        return _RoleFactPresentation(
            tuple(_visitor_object_statement(statement) for statement in source_statements),
            source_statements,
        )
    pairs = _child_role_fact_pairs(source_statements, topic_kind=topic_kind)
    return _RoleFactPresentation(
        tuple(summary for summary, _ in pairs),
        tuple(source for _, source in pairs),
    )


def _role_unit_lead_in(*, style_id: str, topic_kind: str, name: str) -> str | None:
    """Return a fact-free lead-in, if this presentation policy uses one."""
    if style_id != "child":
        return None
    if topic_kind == "craft":
        return f"第一条小线索，是一种叫作“{name}”的传统工艺。"
    if topic_kind == "ornament":
        return f"接着和{name}这位新朋友打个招呼。"
    return None


def _craft_segment(
    craft: str, packet: EvidencePacket, style: NarrationStylePolicy | None, style_id: str
) -> tuple[list[str], tuple[str, ...], bool, str | None, tuple[str, ...]]:
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
        return [], (), False, f"{craft}缺少可用于首次介绍的工艺证据", ()
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
    return lines, source_ids, complete, warning, tuple(
        sentence for sentence, _ in visitor_selected
    )


def _ornament_segment(
    item: Any,
    packet: EvidencePacket,
    location: Any,
    *,
    first: bool,
    detailed: bool,
    style: NarrationStylePolicy | None,
    style_id: str,
) -> tuple[list[str], tuple[str, ...], bool, str | None, tuple[str, ...]]:
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
        detailed=detailed,
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
    return lines, source_ids, complete if first else False, warning, tuple(lines)


def _optional_context_segment(
    packet: EvidencePacket | None,
    program: StopProgram,
    *,
    detailed: bool,
) -> tuple[list[str], tuple[str, ...], tuple[str, ...]]:
    """Select a small, sourced enrichment without making it mandatory.

    Semantic retrieval chooses candidate sections for the reviewed point
    profile.  This final deterministic gate keeps only sentences tied to a
    selected object, craft, stop or visible component and never exposes
    editorial/source-boundary prose to visitors.
    """
    if packet is None or not packet.evidence or program.budget_seconds < 210:
        return [], (), ()
    anchors = (
        program.display_name,
        *(item.name for item in program.selected_items),
        *(item.craft for item in program.selected_items),
    )
    ranked: list[tuple[int, str, tuple[str, ...], str]] = []
    for entry in packet.evidence:
        one_entry = EvidencePacket(
            packet.evidence_kind, packet.subject_id, packet.query,
            (entry,), tuple(entry.get("source_ids", ())), packet.retrieval_error,
        )
        dimension_id = optional_dimension_id(entry)
        for sentence, source_ids in _sentences(one_entry):
            cleaned = _visitor_object_statement(sentence).strip()
            if (
                len(cleaned) < 12
                or len(cleaned) > 150
                or any(marker in cleaned for marker in OPTIONAL_CONTEXT_SKIP_MARKERS)
            ):
                continue
            score = sum(8 for item in program.selected_items if item.name in cleaned)
            score += sum(4 for item in program.selected_items if item.craft in cleaned)
            score += sum(3 for interest in program.interests if interest and interest in cleaned)
            score += 2 if program.display_name in cleaned else 0
            if score:
                ranked.append((score, cleaned, source_ids, dimension_id))
    ranked.sort(key=lambda value: (-value[0], len(value[1]), value[1]))
    limit = 2 if detailed and program.budget_seconds >= 270 else 1
    chosen: list[str] = []
    sources: set[str] = set()
    dimension_ids: list[str] = []
    for _, sentence, source_ids, dimension_id in ranked:
        if sentence in chosen:
            continue
        if dimension_id in dimension_ids:
            continue
        chosen.append(sentence)
        sources.update(source_ids)
        dimension_ids.append(dimension_id)
        if len(chosen) >= limit:
            break
    return chosen, tuple(sorted(sources)), tuple(dimension_ids)


def _rhetorical_observation(
    program: StopProgram,
    rendered_items: tuple[Any, ...],
    bundle: GuidanceEvidenceBundle,
    *,
    detailed: bool,
    style_id: str,
) -> str | None:
    """Return one self-contained observation question and its answer.

    The question never asks the visitor to respond.  Its answer uses only the
    selected object's reviewed craft and location, avoiding a new historical,
    symbolic or causal claim that is absent from the evidence bundle.
    """
    depth_allows = detailed or program.detail_level == "deep"
    if not depth_allows or program.budget_seconds < 210 or style_id == "listen_only" or not rendered_items:
        return None
    item = rendered_items[0]
    location = bundle.location_evidence.get(item.ornament_id)
    raw_location = (
        str(location.raw_location).strip()
        if location is not None and getattr(location, "valid", False) and location.raw_location
        else "所在建筑构件"
    )
    return (
        f"为什么观察{item.name}时，既要看造型，也要看它所在的位置？"
        f"因为它不是脱离建筑陈设的独立摆件；把{raw_location}与{item.craft}的造型放在一起看，"
        "更容易理解装饰与建筑构件之间的关系。"
    )


def render_guidance_evidence(
    program: StopProgram,
    bundle: GuidanceEvidenceBundle,
    guidance_policy: GuidancePolicy | dict[str, Any] | None = None,
    *,
    detailed: bool = False,
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
    elif components := stop_guidance_compatibility_components(style):
        # This is the deterministic compatibility path used when the role
        # candidate is unavailable or deliberately shadowed.  It must still
        # sound like the selected role rather than falling back to a neutral
        # catalogue dump.  The phrase is reviewed, fact-free and is replaced
        # (not duplicated) if the active role candidate later publishes.  Its
        # dedicated adapter prevents route/arrival paths from borrowing it.
        if components.opening:
            lines.append(components.opening)
    rendered_crafts: list[str] = []
    rendered_ornaments: list[str] = []
    used_sources: set[str] = set()
    warnings: list[str] = []
    fact_units: list[dict[str, Any]] = []
    eligible: list[CoverageCandidate] = []
    eligible_by_subject = {(candidate.subject_kind, candidate.subject_id): candidate for candidate in bundle.coverage_candidates}

    crafts_in_prefix = tuple(dict.fromkeys(item.craft for item in rendered_items))
    for craft in crafts_in_prefix:
        status = bundle.coverage_status["craft"].get(craft)
        if status == "first_introduction":
            packet = bundle.craft_overviews.get(craft)
            if packet and packet.evidence:
                segment, sources, complete, warning, statements = _craft_segment(craft, packet, style, style_id)
                presentation = _role_fact_presentation(
                    statements, topic_kind="craft", style_id=style_id,
                )
                role_statements = presentation.statements
                if lead_in := _role_unit_lead_in(
                    style_id=style_id, topic_kind="craft", name=craft,
                ):
                    lines.append(lead_in)
                    lines.extend(role_statements)
                else:
                    # Deterministic narration must read as one guided walk,
                    # not as a stack of catalogue cards.  Keep the reviewed
                    # facts, but let the first factual sentence introduce the
                    # craft naturally instead of printing a bracketed label.
                    lines.extend(_visitor_object_statement(line) for line in segment)
                if statements:
                    unit = {
                        "unit_id": f"craft:{craft}",
                        "topic_kind": "craft",
                        "statements": list(role_statements),
                        "required": True,
                    }
                    unit["source_statements"] = list(presentation.source_statements)
                    fact_units.append(unit)
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
        segment, sources, complete, warning, statements = _ornament_segment(
            item, packet, bundle.location_evidence.get(item.ornament_id), first=first,
            detailed=detailed, style=style, style_id=style_id,
        )
        presentation = _role_fact_presentation(
            statements, topic_kind="ornament", style_id=style_id,
        )
        role_statements = presentation.statements
        if lead_in := _role_unit_lead_in(
            style_id=style_id, topic_kind="ornament", name=item.name,
        ):
            lines.append(lead_in)
            lines.extend(role_statements)
        else:
            # Keep every reviewed object as plain prose.  The object's first
            # factual sentence names it, so a separate bracketed heading is
            # redundant and makes the guide sound like a database export.
            lines.extend(_visitor_object_statement(line) for line in segment)
        if statements:
            unit = {
                "unit_id": f"ornament:{item.ornament_id}",
                "topic_kind": "ornament",
                "statements": list(role_statements),
                "required": True,
            }
            unit["source_statements"] = list(presentation.source_statements)
            fact_units.append(unit)
        rendered_ornaments.append(item.ornament_id)
        used_sources.update(sources)
        if complete and (candidate := eligible_by_subject.get(("ornament", item.ornament_id))):
            eligible.append(candidate)
        if warning:
            warnings.append(warning)

    optional_lines, optional_sources, optional_dimension_ids = _optional_context_segment(
        bundle.optional_context, program, detailed=detailed,
    )
    if optional_lines:
        lines.extend(optional_lines)
        used_sources.update(optional_sources)
        for dimension_id, statement in zip(optional_dimension_ids, optional_lines):
            fact_units.append({
                "unit_id": f"dimension:{dimension_id}",
                "topic_kind": "dimension",
                "statements": [statement],
                "source_statements": [statement],
                "required": False,
            })
            if candidate := eligible_by_subject.get(("dimension", dimension_id)):
                eligible.append(candidate)

    rhetorical = _rhetorical_observation(
        program, rendered_items, bundle, detailed=detailed, style_id=style_id,
    )
    if rhetorical:
        lines.append(rhetorical)

    if len(rendered_ornaments) >= 2:
        first, second = rendered_items[0], rendered_items[1]
        if first.craft == second.craft:
            lines.append(f"这两件都属于{first.craft}，可以对照它们各自的造型处理。")
        else:
            lines.append("也可以留意两种工艺在构件处理上的不同。")
    if omitted:
        warnings.append("本站预算优先保留核心对象，后续对象留待需要时再展开")
    if (
        policy
        and policy.interaction_mode != "listen_only"
        and policy.interaction_task_enabled
        and not rhetorical
    ):
        lines.append("您可以留意其中一处造型细部；无需回答也不影响继续导览。")
    # The completion instruction is deliberately a peer paragraph, rather
    # than the last line of an object or observation paragraph.
    if style_id == "child":
        lines.append("这一站的小秘密先看到这里。我们慢慢来，想仔细看看或完成本点都可以。")
    lines.append(COMPLETION_PROMPT)
    allocated = sum(item.planned_seconds for item in rendered_items)
    return NarrationRenderResult(
        visitor_message="\n\n".join(lines),
        rendered_craft_ids=tuple(rendered_crafts),
        rendered_ornament_ids=tuple(rendered_ornaments),
        rendered_dimension_ids=optional_dimension_ids,
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
        fact_units=tuple(fact_units),
    )
