"""Evidence-bounded rendering for reviewed visitor facts and calculations.

This module owns neither retrieval nor tour state.  It recognizes a deliberately
small set of high-confidence questions, chooses the reviewed RAG category scope,
and turns returned evidence into a conclusion-first visitor answer.  Source IDs
and evidence indexes remain available only in the audit record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from controlled_derivation import (
    ControlledDerivationError,
    DerivedOperand,
    deterministic_difference,
)


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
INTERNAL_TOKENS = (
    ".md",
    "title_path",
    "source_ids",
    "chunk_id",
    "node_id",
    "http://",
    "https://",
)
YEAR_PATTERN = r"(?:18|19|20)\d{2}"
TIME_PATTERN = r"(?:[01]?\d|2[0-3]):[0-5]\d"
VISIT_SERVICE_CATEGORIES = ("basic_info", "visit_service", "ticketing_snapshot")
FACT_KINDS = frozenset(
    {
        "construction_start",
        "construction_completion",
        "construction_duration",
        "site_address",
        "closed_day",
        "closing_time",
        "last_admission",
        "afternoon_entry_cutoff",
        "identity_admission_workaround",
        "designer_and_foundation_date",
    }
)


@dataclass(frozen=True)
class SingleFactAnswer:
    """One visitor-facing conclusion plus a machine-readable audit record."""

    fact_kind: str
    message: str
    source_ids: tuple[str, ...]
    evidence_indexes: tuple[int, ...]
    ok: bool
    evidence_categories: tuple[str, ...] = ()
    calculation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact(user_query: str) -> str:
    return "".join(str(user_query or "").split())


def identify_single_fact_kind(user_query: str) -> str | None:
    """Recognize only explicit, high-confidence reviewed question shapes."""

    text = _compact(user_query)
    if not text:
        return None

    has_site = any(name in text for name in SITE_NAMES)
    if has_site and (
        any(term in text for term in ("由谁设计", "谁设计", "设计者", "设计人"))
        or any(term in text for term in ("奠基", "动工日期"))
    ):
        return "designer_and_foundation_date"
    if (
        has_site
        and any(term in text for term in CONSTRUCTION_START_TERMS)
        and any(term in text for term in ("落成", "建成", "竣工"))
        and any(term in text for term in ("多久", "多少年", "经历", "相隔", "时间差"))
    ):
        return "construction_duration"
    if has_site and any(term in text for term in ADDRESS_TERMS):
        return "site_address"

    # Service questions are safe to resolve without repeating the site name:
    # the application has one fixed venue, and these phrases are unambiguous.
    if (
        any(term in text for term in ("身份证", "身份证件", "证件"))
        and (
            any(
                term in text
                for term in (
                    "忘带",
                    "没带",
                    "未带",
                    "没有带",
                    "没拿",
                    "未携带",
                    "丢了",
                )
            )
            or any(
                term in text
                for term in (
                    "电子身份证",
                    "电子证件",
                    "身份证照片",
                    "照片代替",
                    "替代证件",
                    "其他证件",
                )
            )
        )
        and any(
            term in text
            for term in (
                "能不能进",
                "可以进",
                "入馆",
                "进馆",
                "入场",
                "检票",
                "订了票",
                "怎么办",
            )
        )
    ):
        return "identity_admission_workaround"
    if "周二" in text and any(term in text for term in ("开放", "闭馆", "休馆", "开门")):
        return "closed_day"
    if "下午场" in text and any(term in text for term in ("检票", "入场", "入馆")):
        return "afternoon_entry_cutoff"
    if any(term in text for term in ("停止入场", "停止入馆", "最晚入场", "最晚入馆")):
        return "last_admission"
    if (
        any(term in text for term in ("闭馆时间", "几点闭馆", "什么时候闭馆", "何时闭馆", "几点关门"))
        and "周二" not in text
    ):
        return "closing_time"

    if not has_site:
        return None
    if any(term in text for term in CONSTRUCTION_START_TERMS):
        return "construction_start"
    if any(term in text for term in CONSTRUCTION_COMPLETION_TERMS):
        return "construction_completion"
    return None


def single_fact_categories(user_query: str) -> list[str] | None:
    """Return the reviewed category scope shared by both QA modes."""

    return single_fact_categories_for_kind(identify_single_fact_kind(user_query))


def single_fact_categories_for_kind(fact_kind: str | None) -> list[str] | None:
    """Return the reviewed category scope for a validated fact kind."""

    if fact_kind == "site_address":
        return ["basic_info"]
    if fact_kind in {
        "construction_start",
        "construction_completion",
        "construction_duration",
        "designer_and_foundation_date",
    }:
        return ["history_architecture"]
    if fact_kind == "closed_day":
        return list(VISIT_SERVICE_CATEGORIES)
    if fact_kind == "closing_time":
        return ["basic_info", "ticketing_snapshot"]
    if fact_kind == "last_admission":
        return list(VISIT_SERVICE_CATEGORIES)
    if fact_kind == "afternoon_entry_cutoff":
        return ["ticketing_snapshot"]
    if fact_kind == "identity_admission_workaround":
        return ["ticketing_snapshot", "visit_service"]
    return None


def single_fact_retrieval_query(user_query: str) -> str:
    """Use stable evidence terms instead of mode-dependent query expansion."""

    return single_fact_retrieval_query_for_kind(
        identify_single_fact_kind(user_query), fallback=user_query
    )


def single_fact_retrieval_query_for_kind(
    fact_kind: str | None, *, fallback: str = ""
) -> str:
    """Return a deterministic query rewrite for a validated fact kind."""

    return {
        "construction_start": "陈家祠 1888年 开始筹建 建祠公所",
        "construction_completion": "陈家祠 1888年筹建 1893年落成 1894年建成 来源差异",
        "construction_duration": "陈家祠 1888年筹建 1893年落成 1894年建成",
        "designer_and_foundation_date": "陈家祠 设计者 奠基日期 历史沿革",
        "site_address": "陈家祠 地址 馆址 恩龙里34号",
        "closed_day": "陈家祠 常规闭馆日 周二 法定节假日",
        "closing_time": "陈家祠 常规开放时间 闭馆时间 延时开放 18:00",
        "last_admission": "陈家祠 停止入场 停止入馆 17:00 延时开放",
        "afternoon_entry_cutoff": "陈家祠 下午场 检票时段 截止 17:00 17:30",
        "identity_admission_workaround": (
            "陈家祠 忘带身份证 未携带身份证件 综合服务处 "
            "电子身份证 其他有效证件 换取实体票 入馆"
        ),
    }.get(fact_kind, fallback)


def _source_ids(items: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            source_id
            for item in items
            for source_id in item.get("source_ids", ())
            if isinstance(source_id, str) and source_id.strip()
        )
    )


def _categories(items: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            category
            for item in items
            if isinstance((category := item.get("category")), str) and category
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


def _construction_evidence(
    evidence: list[dict[str, Any]],
) -> tuple[list[tuple[int, dict[str, Any]]], list[int], list[int]]:
    relevant: list[tuple[int, dict[str, Any]]] = []
    start_years: list[int] = []
    completion_years: list[int] = []
    start_patterns = (
        rf"(?P<year>{YEAR_PATTERN})\s*年[^。\n]{{0,80}}(?:开始筹建|筹建|建祠公所成立)",
        rf"(?:开始筹建|筹建|始建(?:于)?)[^。\n]{{0,30}}(?P<year>{YEAR_PATTERN})\s*年",
    )
    completion_patterns = (
        rf"(?P<year>{YEAR_PATTERN})\s*年\s*(?:落成|建成|竣工)",
    )
    for index, item in enumerate(evidence):
        content = str(item.get("content") or "")
        item_start_years = _years(content, start_patterns)
        item_completion_years = _years(content, completion_patterns)
        if not item_start_years and not item_completion_years:
            continue
        relevant.append((index, item))
        start_years.extend(year for year in item_start_years if year not in start_years)
        completion_years.extend(
            year for year in item_completion_years if year not in completion_years
        )
    return relevant, sorted(start_years), sorted(completion_years)


def _construction_answer(
    fact_kind: str, evidence: list[dict[str, Any]]
) -> SingleFactAnswer:
    relevant, start_years, completion_years = _construction_evidence(evidence)
    relevant_items = [item for _, item in relevant]
    source_ids = _source_ids(relevant_items)
    evidence_indexes = tuple(index for index, _ in relevant)
    categories = _categories(relevant_items)

    if fact_kind == "designer_and_foundation_date":
        # The reviewed history evidence currently identifies advocates and
        # construction years, not a designer or an exact foundation date.
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=(
                "现有资料不足以确认陈家祠的设计者和确切奠基日期。"
                "资料中提到的倡议人不能直接等同于建筑设计者，因此不作推测。"
            ),
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            evidence_categories=categories,
            ok=False,
        )

    if fact_kind == "construction_start" and start_years and source_ids:
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=(
                f"陈家祠于 {start_years[0]} 年开始筹建。"
                "这一年份指筹建启动，不是落成年份。"
            ),
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            evidence_categories=categories,
            ok=True,
        )

    if fact_kind == "construction_completion" and completion_years and source_ids:
        start = (
            f"{start_years[0]} 年是开始筹建的年份；" if start_years else ""
        )
        if len(completion_years) >= 2:
            first, second = completion_years[:2]
            conclusion = (
                f"公开资料对落成或建成年份有两种表述：{first} 年落成和 "
                f"{second} 年建成。"
                + (
                    f"陈家祠于 {start_years[0]} 年开始筹建；"
                    if start_years
                    else ""
                )
                + "这是资料口径差异，不宜把其中一个年份作为唯一结论。"
            )
        else:
            conclusion = (
                f"现有资料记载陈家祠于 {completion_years[0]} 年落成或建成。{start}"
            )
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=conclusion,
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            evidence_categories=categories,
            ok=True,
        )

    if (
        fact_kind == "construction_duration"
        and start_years
        and completion_years
        and source_ids
    ):
        start_year = start_years[0]
        try:
            derivations = [
                deterministic_difference(
                    operation="time_difference",
                    start=DerivedOperand(
                        label="开始筹建",
                        value=start_year,
                        evidence_indexes=evidence_indexes,
                    ),
                    end=DerivedOperand(
                        label=f"{year} 年落成或建成",
                        value=year,
                        evidence_indexes=evidence_indexes,
                    ),
                    unit="年",
                )
                for year in completion_years
            ]
        except ControlledDerivationError:
            derivations = []
        results = [
            {
                "completion_year": int(item["end"]["value"]),
                "years": int(item["difference"]),
            }
            for item in derivations
        ]
        if results:
            if len(results) >= 2:
                details = "；".join(
                    f"按 {item['completion_year']} 年口径约 {item['years']} 年"
                    for item in results[:2]
                )
                year_differences = [item["years"] for item in results[:2]]
                message = (
                    "陈家祠从筹建到落成大约经历了 "
                    f"{min(year_differences)} 至 {max(year_differences)} 年：{details}。"
                    "这是根据不同公开资料的落成年份口径作出的确定性年份差计算。"
                )
            else:
                item = results[0]
                message = (
                    f"按现有资料口径，从 {start_year} 年筹建到 "
                    f"{item['completion_year']} 年落成约 {item['years']} 年。"
                )
            return SingleFactAnswer(
                fact_kind=fact_kind,
                message=message,
                source_ids=source_ids,
                evidence_indexes=evidence_indexes,
                evidence_categories=categories,
                calculation={
                    "operation": "year_difference",
                    "start_year": start_year,
                    "results": results,
                    "derivations": derivations,
                    "deterministic": True,
                },
                ok=True,
            )

    subject = {
        "construction_start": "开始筹建时间",
        "construction_completion": "落成或建成时间",
        "construction_duration": "筹建到落成的时间差",
    }.get(fact_kind, "所问历史事实")
    return SingleFactAnswer(
        fact_kind=fact_kind,
        message=f"现有资料不足以确认陈家祠的{subject}，因此不作推测。",
        source_ids=source_ids,
        evidence_indexes=evidence_indexes,
        evidence_categories=categories,
        ok=False,
    )


def _address_answer(evidence: list[dict[str, Any]]) -> SingleFactAnswer:
    matches: list[tuple[int, dict[str, Any], str]] = []
    for index, item in enumerate(evidence):
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
    categories = _categories(relevant_items)
    if matches and source_ids:
        return SingleFactAnswer(
            fact_kind="site_address",
            message=f"陈家祠的地址是{matches[0][2]}。",
            source_ids=source_ids,
            evidence_indexes=evidence_indexes,
            evidence_categories=categories,
            ok=True,
        )
    return SingleFactAnswer(
        fact_kind="site_address",
        message="现有基础信息证据不足以确认陈家祠的具体地址，因此不作推测。",
        source_ids=source_ids,
        evidence_indexes=evidence_indexes,
        evidence_categories=categories,
        ok=False,
    )


def _service_items(
    evidence: list[dict[str, Any]], patterns: tuple[str, ...]
) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, item)
        for index, item in enumerate(evidence)
        if _source_ids([item])
        and any(pattern in str(item.get("content") or "") for pattern in patterns)
    ]


def _service_answer(
    fact_kind: str, evidence: list[dict[str, Any]]
) -> SingleFactAnswer:
    patterns = {
        "closed_day": ("周二闭馆", "闭馆日为每周二", "常规闭馆日：每周二"),
        "closing_time": ("常规开放时间", "闭馆时间延至"),
        "last_admission": ("停止入场", "停止入馆", "下午场检票截止"),
        "afternoon_entry_cutoff": ("下午场检票时段", "下午场检票截止"),
    }[fact_kind]
    relevant = _service_items(evidence, patterns)
    relevant_items = [item for _, item in relevant]
    source_ids = _source_ids(relevant_items)
    indexes = tuple(index for index, _ in relevant)
    categories = _categories(relevant_items)
    combined = "\n".join(str(item.get("content") or "") for item in relevant_items)
    freshness = "开放安排可能调整，请以官方当日公告为准。"

    message: str | None = None
    if fact_kind == "closed_day" and "周二" in combined and "闭馆" in combined:
        message = f"陈家祠常规每周二闭馆，法定节假日除外。{freshness}"
    elif fact_kind == "closing_time":
        normal = re.search(
            rf"常规开放时间[：:]\s*{TIME_PATTERN}\s*[–—-]\s*(?P<time>{TIME_PATTERN})",
            combined,
        )
        extended = re.search(
            rf"闭馆时间延至\s*(?P<time>{TIME_PATTERN})", combined
        )
        if normal:
            message = f"常规开放时段到 {normal.group('time')}。"
            if extended:
                message += (
                    f"4 月 15 日至 10 月 15 日的延时开放资料记载闭馆时间延至 "
                    f"{extended.group('time')}。"
                )
            message += (
                "停止入场或售票时间与正式闭馆时间不是同一概念。"
                + freshness
            )
        elif extended:
            message = (
                f"现有资料只能确认延时开放期间闭馆时间延至 {extended.group('time')}，"
                f"不能据此推断常规闭馆时间。{freshness}"
            )
    elif fact_kind == "last_admission":
        normal = re.search(
            rf"(?:停止入场|停止入馆)[^0-9]{{0,8}}(?P<time>{TIME_PATTERN})|"
            rf"(?P<time_before>{TIME_PATTERN})\s*停止(?:入场|入馆)",
            combined,
        )
        if normal:
            normal_time = normal.group("time") or normal.group("time_before")
            message = f"常规停止入场时间为 {normal_time}。"
            if "下午场检票截止和当日售票截止延至 17:30" in combined:
                message += (
                    "4 月 15 日至 10 月 15 日延时开放期间，"
                    "下午场检票和当日售票截止延至 17:30。"
                )
            message += "这不是正式闭馆时间。" + freshness
    elif fact_kind == "afternoon_entry_cutoff":
        normal = re.search(
            rf"下午场检票时段[：:]\s*{TIME_PATTERN}\s*[–—-]\s*(?P<time>{TIME_PATTERN})",
            combined,
        )
        if normal:
            message = f"下午场常规检票截止到 {normal.group('time')}。"
            if "下午场检票截止和当日售票截止延至 17:30" in combined:
                message += (
                    "4 月 15 日至 10 月 15 日延时开放期间，"
                    "下午场检票截止延至 17:30。"
                )
            message += freshness

    if message is not None and source_ids:
        return SingleFactAnswer(
            fact_kind=fact_kind,
            message=message,
            source_ids=source_ids,
            evidence_indexes=indexes,
            evidence_categories=categories,
            ok=True,
        )
    labels = {
        "closed_day": "常规闭馆日",
        "closing_time": "正式闭馆时间",
        "last_admission": "停止入场时间",
        "afternoon_entry_cutoff": "下午场检票截止时间",
    }
    return SingleFactAnswer(
        fact_kind=fact_kind,
        message=(
            f"现有访问服务证据不足以确认{labels[fact_kind]}。"
            f"{freshness}"
        ),
        source_ids=source_ids,
        evidence_indexes=indexes,
        evidence_categories=categories,
        ok=False,
    )


def _identity_admission_answer(
    evidence: list[dict[str, Any]],
) -> SingleFactAnswer:
    """Render the reviewed workaround without treating a normal rule as a ban."""

    required_terms = (
        "未携带身份证件",
        "综合服务处",
        "换取实体票",
    )
    relevant: list[tuple[int, dict[str, Any]]] = []
    workaround_found = False
    for index, item in enumerate(evidence):
        content = str(item.get("content") or "")
        if any(
            term in content
            for term in (
                "身份证原件",
                "身份证件",
                "电子身份证",
                "其他有效证件",
                "综合服务处",
                "实体票",
            )
        ):
            relevant.append((index, item))
        if (
            all(term in content for term in required_terms)
            and any(term in content for term in ("电子身份证", "其他有效证件"))
        ):
            workaround_found = True

    relevant_items = [item for _, item in relevant]
    source_ids = _source_ids(relevant_items)
    indexes = tuple(index for index, _ in relevant)
    categories = _categories(relevant_items)
    freshness = "具体核验安排可能调整，请以馆方当日要求为准。"

    if workaround_found and source_ids:
        message = (
            "有替代处理方式。已完成订票但未携带身份证件时，可到综合服务处"
            "出示电子身份证或其他有效证件，换取实体票后按现场流程入馆。"
            "使用优惠票或免票的游客，仍应按要求出示相应有效证件供查验。"
            + freshness
        )
        return SingleFactAnswer(
            fact_kind="identity_admission_workaround",
            message=message,
            source_ids=source_ids,
            evidence_indexes=indexes,
            evidence_categories=categories,
            ok=True,
        )

    return SingleFactAnswer(
        fact_kind="identity_admission_workaround",
        message=(
            "现有资料不足以确认忘带身份证后的替代入馆方式，"
            "不能仅凭通常要求携带身份证原件就得出否定结论。"
            + freshness
        ),
        source_ids=source_ids,
        evidence_indexes=indexes,
        evidence_categories=categories,
        ok=False,
    )


def _validate_visitor_message(message: str) -> None:
    if any(token in message for token in INTERNAL_TOKENS):
        raise ValueError("游客文本包含内部检索字段或链接。")
    if re.search(r"(?<![A-Za-z0-9])S\d{1,3}(?![A-Za-z0-9])", message):
        raise ValueError("游客文本包含内部来源编号。")


def render_single_fact_answer(
    user_query: str,
    evidence: list[dict[str, Any]] | None,
    *,
    fact_kind: str | None = None,
) -> SingleFactAnswer | None:
    """Return a controlled answer, or ``None`` for an unreviewed question."""

    resolved_fact_kind = fact_kind or identify_single_fact_kind(user_query)
    if resolved_fact_kind not in FACT_KINDS:
        return None
    normalized_evidence = [
        item for item in (evidence or []) if isinstance(item, dict)
    ]
    if resolved_fact_kind == "site_address":
        result = _address_answer(normalized_evidence)
    elif resolved_fact_kind == "identity_admission_workaround":
        result = _identity_admission_answer(normalized_evidence)
    elif resolved_fact_kind in {
        "construction_start",
        "construction_completion",
        "construction_duration",
        "designer_and_foundation_date",
    }:
        result = _construction_answer(resolved_fact_kind, normalized_evidence)
    else:
        result = _service_answer(resolved_fact_kind, normalized_evidence)
    _validate_visitor_message(result.message)
    return result
