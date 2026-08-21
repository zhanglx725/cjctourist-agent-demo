"""Safety gates and deterministic ranking for expanded knowledge domains."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


DOMAIN_DOCUMENTS = {
    "people_craftspeople": frozenset({"10_people_builders_craftspeople.md"}),
    "architectural_conservation": frozenset({"11_architectural_conservation.md", "02_history_architecture.md"}),
    "craft_process": frozenset({"12_craft_process_and_transmission.md", "07_ornament_crafts.md"}),
    "literary_citation": frozenset({"13_literary_citation_cards.md"}),
    "education_examination": frozenset({"14_students_examinations_and_education.md", "02_history_architecture.md"}),
}

ATTRIBUTION_MARKERS = ("馆方", "公开", "资料", "记载", "采访", "档案", "地方志", "碑刻", "论文", "来源")
TIME_BOUNDARY_MARKERS = ("年", "历史", "曾", "当时", "目前", "当前", "截至", "资料日期", "整理日期")
LITERARY_REQUIRED_MARKERS = ("原文", "作者", "篇名", "版本或来源", "对应装饰或点位", "是否允许逐字引用")
LITERARY_RELATION_MARKERS = ("直接相关", "借用诗意", "后人对陈家祠的评价", "A 类", "B 类", "C 类")
EDUCATION_BOUNDARY_MARKERS = ("应试", "应考", "科举", "暂住", "办学", "书院", "章程", "题名", "证据")


def _document(item: dict[str, Any]) -> str:
    return Path(str(item.get("document") or "")).name


def evidence_identity(item: dict[str, Any]) -> str:
    chunk_id = str(item.get("chunk_id") or "").strip()
    if chunk_id:
        return chunk_id
    return "|".join((
        _document(item),
        "/".join(str(value) for value in item.get("title_path") or ()),
        str(item.get("content") or "")[:160],
    ))


def evidence_is_safe_for_domain(domain: str, item: dict[str, Any]) -> bool:
    """Apply domain-specific proof thresholds before model synthesis."""
    content = str(item.get("content") or "").strip()
    if not content:
        return False
    allowed_documents = DOMAIN_DOCUMENTS.get(domain)
    if allowed_documents is None:
        return True
    if not item.get("source_ids"):
        return False
    if allowed_documents is not None and _document(item) not in allowed_documents:
        return False
    if domain == "people_craftspeople":
        return any(marker in content for marker in ATTRIBUTION_MARKERS)
    if domain == "architectural_conservation":
        return any(marker in content for marker in ATTRIBUTION_MARKERS) and any(
            marker in content for marker in TIME_BOUNDARY_MARKERS
        )
    if domain == "literary_citation":
        return all(marker in content for marker in LITERARY_REQUIRED_MARKERS) and any(
            marker in content for marker in LITERARY_RELATION_MARKERS
        )
    if domain == "education_examination":
        return any(marker in content for marker in ATTRIBUTION_MARKERS) and any(
            marker in content for marker in EDUCATION_BOUNDARY_MARKERS
        )
    return True


def retrieval_limit_for_plan(detail_level: str, category_count: int = 1) -> int:
    """Use a larger bounded pool for detailed or cross-category questions."""
    if detail_level == "detailed":
        return 8
    return 5 if category_count > 1 else 4


def retrieval_limit_for_question(question: str) -> int:
    """Estimate a bounded evidence pool from explicit breadth/detail cues."""
    text = str(question or "")
    detailed = any(token in text for token in ("详细", "深入", "展开", "全面", "系统", "多讲", "再讲"))
    domain_groups = (
        ("人物", "工匠", "传承人", "谁"),
        ("保护", "修缮", "修复", "病害"),
        ("制作", "工序", "材料", "工具"),
        ("诗文", "文学", "出处", "引用"),
        ("科举", "应试", "学子", "教育"),
        ("历史", "建筑", "空间", "城市"),
    )
    breadth = sum(1 for group in domain_groups if any(token in text for token in group))
    if detailed or breadth >= 3:
        return 8
    if breadth >= 2:
        return 6
    return 4


def rank_domain_evidence(
    domain: str,
    subject_text: str,
    evidence: Iterable[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Deduplicate and rank exact-domain evidence ahead of broad neighbours."""
    subject_terms = tuple(
        term for term in str(subject_text).replace("？", "").replace("?", "").split()
        if len(term) >= 2
    )
    preferred = DOMAIN_DOCUMENTS.get(domain, frozenset())
    seen: set[str] = set()
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for item in evidence:
        if not isinstance(item, dict) or not evidence_is_safe_for_domain(domain, item):
            continue
        identity = evidence_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        haystack = " ".join((
            "/".join(str(value) for value in item.get("title_path") or ()),
            str(item.get("content") or ""),
        ))
        score = 20 if _document(item) in preferred else 0
        score += sum(3 for term in subject_terms if term in haystack)
        score += min(len(item.get("source_ids") or ()), 3)
        ranked.append((score, identity, item))
    ranked.sort(key=lambda value: (-value[0], value[1]))
    return [item for _, _, item in ranked[:limit]]


def optional_narration_evidence_is_safe(item: dict[str, Any]) -> bool:
    """Infer the curated document's safety domain for point narration."""
    document = _document(item)
    matching_domains = [
        domain for domain, documents in DOMAIN_DOCUMENTS.items()
        if document in documents
    ]
    return any(evidence_is_safe_for_domain(domain, item) for domain in matching_domains)
