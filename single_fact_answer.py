"""Evidence-bounded rendering for a small set of single-fact questions.

The renderer never retrieves data and never treats code constants as site
facts.  It recognizes a reviewed question shape, extracts only the requested
fact from RAG evidence, and fails closed when that evidence is insufficient.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable


SITE_NAMES = ("陈家祠", "陈氏书院")
CONSTRUCTION_START_TERMS = ("始建", "筹建", "开始建")
CONSTRUCTION_COMPLETION_TERMS = (
    "建成",
    "落成",
    "竣工",
    "建于",
    "修建于",
    "哪年修建",
    "何时建",
    "哪年建",
    "哪一年建",
    "什么时候建",
)
ADDRESS_TERMS = (
    "地址",
    "馆址",
    "在哪里",
    "在哪儿",
    "位于哪里",
    "在什么地方",
    "坐落在哪里",
)
INTERNAL_TOKENS = (".md", "title_path", "source_ids", "chunk_id")
YEAR_PATTERN = r"(?:18|19|20)\d{2}"


@dataclass(frozen=True)
class SingleFactAnswer:
    """One visitor-facing conclusion plus a compact audit record."""

    fact_kind: str
    message: str
    source_ids: tuple[str, ...]
    evidence_indexes: tuple[int, ...]
    ok: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def identify_single_fact_kind(user_query: str) -> str | None:
    """Recognize only explicit, high-confidence single-fact questions."""

    text = "".join(str(user_query or "").split())
    if not text or not any(name in text for name in SITE_NAMES):
        return None
    if any(term in text for term in ADDRESS_TERMS):
        return "site_address"
    if any(term in text for term in CONSTRUCTION_START_TERMS):
        return "construction_start"
    if any(term in text for term in CONSTRUCTION_COMPLETION_TERMS):
        return "construction_completion"
    return None


def single_fact_categories(user_query: str) -> list[str] | None:
    """Return the existing RAG category scope for one reviewed fact kind."""

    fact_kind = identify_single_fact_kind(user_query)
    if fact_kind == "site_address":
        return ["basic_info"]
    if fact_kind in {"construction_start", "construction_completion"}:
        return ["history_architecture"]
    return None


def _source_ids(items: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            source_id
            for item in items
            for source_id in item.get("source_ids", ())
            if isinstance(source_id, str) and source_id.strip()
        )
    )


def _years(content: str, patterns: tuple[str, ...]) -> tuple[int, ...]:
    found: list[int] = []
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            year = int(match.group("year"))
            if year not in found:
                found.append(year)
    return tuple(found)


def _construction_answer(
    fact_kind: str, evidence: list[dict[str, Any]]
) -> SingleFactAnswer:
    relevant: list[tuple[int, dict[str, Any]]] = []
    start_years: list[int] = []
    completion_years: list[int] = []
    has_official_history_label = False
    has_city_bureau_label = False

    start_patterns = (
        rf"(?P<year>{YEAR_PATTERN})\s*年[^。\n]{{0,80}}(?:开始筹建|筹建|建祠公所成立)",
        rf"(?:开始筹建|筹建|始建(?:于)?)[^。\n]{{0,30}}(?P<year>{YEAR_PATTERN})\s*年",
    )
    completion_patterns = (
        rf"(?P<year>{YEAR_PATTERN})\s*年\s*(?:落成|建成|竣工)",
    )
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        item_start_years = _years(content, start_patterns)
        item_completion_years = _years(content, completion_patterns)
        if not item_start_years and not item_completion_years:
            continue
        relevant.append((index, item))
        for year in item_start_years:
            if year not in start_years:
                start_years.append(year)
        for year in item_completion_years:
            if year not in completion_years:
                completion_years.append(year)
        has_official_history_label = has_official_history_label or "馆方历史" in content
        has_city_bureau_label = (
            has_city_bureau_label or "文化广电旅游局" in content
        )

    relevant_items = [item for _, item in relevant]
    source_ids = _source_ids(relevant_items)
    evidence_indexes = tuple(index for index, _ in relevant)
    sources = f"（来源：{'、'.join(source_ids)}）" if source_ids else ""

    if fact_kind == "construction_start" and start_years and source_ids:
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=f"陈家祠于 {start_years[0]} 年开始筹建。{sources}",
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            ok=True,
        )

    if fact_kind == "construction_completion" and completion_years and source_ids:
        start = (
            f"陈家祠于 {start_years[0]} 年开始筹建。"
            if start_years
            else ""
        )
        if len(completion_years) >= 2:
            first, second = completion_years[:2]
            if has_official_history_label and has_city_bureau_label:
                distinction = (
                    f"关于落成或建成年份，公开资料存在差异：馆方历史页面记为 "
                    f"{first} 年落成，广州市文化广电旅游局资料记为 "
                    f"{second} 年建成，因此不宜把其中一个年份作为唯一结论。"
                )
            else:
                distinction = (
                    f"关于落成或建成年份，当前证据分别记载为 {first} 年和 "
                    f"{second} 年，存在来源差异，因此不宜作唯一断言。"
                )
        else:
            distinction = (
                f"当前检索证据记载其于 {completion_years[0]} 年落成或建成。"
            )
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=f"{start}{distinction}{sources}",
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            ok=True,
        )

    subject = "开始筹建时间" if fact_kind == "construction_start" else "落成或建成时间"
    return SingleFactAnswer(
        fact_kind=fact_kind,
        message=(
            f"当前检索证据不足，无法确认陈家祠的{subject}；"
            "我不会用未检索到的内容补充。"
        ),
        source_ids=source_ids,
        evidence_indexes=evidence_indexes,
        ok=False,
    )


def _address_answer(evidence: list[dict[str, Any]]) -> SingleFactAnswer:
    matches: list[tuple[int, dict[str, Any], str]] = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        address_match = re.search(r"地址[：:]\s*([^\n。；;]+)", content)
        if address_match:
            matches.append((index, item, address_match.group(1).strip()))
            continue
        venue_match = re.search(r"馆址[：:]\s*([^\n。；;]+)", content)
        if venue_match and any(
            token in venue_match.group(1) for token in ("市", "区", "路", "街", "号")
        ):
            matches.append((index, item, venue_match.group(1).strip()))

    relevant_items = [item for _, item, _ in matches]
    source_ids = _source_ids(relevant_items)
    evidence_indexes = tuple(index for index, _, _ in matches)
    if matches and source_ids:
        address = matches[0][2]
        return SingleFactAnswer(
            fact_kind="site_address",
            message=f"陈家祠的地址是{address}。（来源：{'、'.join(source_ids)}）",
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            ok=True,
        )
    return SingleFactAnswer(
        fact_kind="site_address",
        message=(
            "当前检索证据不足，无法确认陈家祠的具体地址；"
            "我不会用未检索到的内容补充。"
        ),
        source_ids=source_ids,
        evidence_indexes=evidence_indexes,
        ok=False,
    )


def render_single_fact_answer(
    user_query: str, evidence: list[dict[str, Any]] | None
) -> SingleFactAnswer | None:
    """Return a compact evidence-bound answer, or ``None`` for other questions."""

    fact_kind = identify_single_fact_kind(user_query)
    if fact_kind is None:
        return None
    normalized_evidence = [
        item for item in (evidence or []) if isinstance(item, dict)
    ]
    if fact_kind == "site_address":
        result = _address_answer(normalized_evidence)
    else:
        result = _construction_answer(fact_kind, normalized_evidence)
    if any(token in result.message for token in INTERNAL_TOKENS):
        raise ValueError("单一事实游客文本包含内部检索字段。")
    return result
