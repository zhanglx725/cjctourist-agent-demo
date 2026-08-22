"""Evidence-bounded, varied expansions for an already explained tour stop.

The current ornament is an internal retrieval anchor only.  Visitor-facing
detail deliberately comes from the reviewed cross-domain documents 10--14;
it never re-renders the original ornament description or location index.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable, Mapping

from knowledge_evidence_policy import evidence_identity, evidence_is_safe_for_domain
from point_knowledge_profiles import point_knowledge_profile
from rag_ingestion import load_knowledge_chunks
from tour_qa import parse_rag_payload


DOMAIN_CONFIG: dict[str, dict[str, str]] = {
    "people_craftspeople": {
        "document": "10_people_builders_craftspeople.md",
        "label": "人物与传承",
        "query": "人物 营建 工匠 师徒 传承",
        "format": "story_card",
    },
    "architectural_conservation": {
        "document": "11_architectural_conservation.md",
        "label": "保护与修缮",
        "query": "保护 修缮 病害 检测 维护",
        "format": "comparison_card",
    },
    "craft_process": {
        "document": "12_craft_process_and_transmission.md",
        "label": "制作与工艺",
        "query": "制作 工序 材料 工具 传承",
        "format": "process_card",
    },
    "literary_citation": {
        "document": "13_literary_citation_cards.md",
        "label": "文学故事",
        "query": "文学 题材 原文 作者 篇名 导游解释",
        "format": "literary_card",
    },
    "education_examination": {
        "document": "14_students_examinations_and_education.md",
        "label": "书院与教育",
        "query": "书院 科举 应试 旗杆夹石 教育",
        "format": "education_card",
    },
}

_SKIP_SENTENCE = re.compile(
    r"(?:^#|^来源|^原文|^使用边界|^不得|^可讲|^适合讲解|^核验状态|"
    r"^是否允许|^是否为直接|^本文件|^本轮|^RAG|source_ids|https?://)",
    re.IGNORECASE,
)
_LABEL_PREFIX = re.compile(r"^(?:[-*]\s*)?(?:\*\*)?[^：:]{1,18}(?:\*\*)?[：:]\s*")
LAST_RESORT_MESSAGE = (
    "再补两点陈家祠保存下来的工艺线索。\n\n"
    "保护与修缮\n陈家祠公开的保护案例表明，面对缺失或残损的细节，处理前需要先调查历史照片、同类图像和构件原状；证据不足时，并不会凭想象补配。\n\n"
    "制作与传承\n公开的灰塑维护资料同时保留了传统工艺与现代记录：材料、塑形和加彩仍依赖工匠经验，摄影、测绘或检测则帮助确认构件原状。"
)


@dataclass(frozen=True)
class DetailCandidate:
    candidate_id: str
    domain: str
    title: str
    evidence: Mapping[str, Any]
    score: int

    def audit_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "topic_type": self.domain,
            "document": Path(str(self.evidence.get("document") or "")).name,
            "title": self.title,
            "score": self.score,
            "fact_id": evidence_identity(dict(self.evidence)),
            "source_ids": list(self.evidence.get("source_ids") or ()),
        }


def _document(entry: Mapping[str, Any]) -> str:
    return Path(str(entry.get("document") or "")).name


def _title(entry: Mapping[str, Any]) -> str:
    values = entry.get("title_path") or ()
    return " · ".join(str(value).strip() for value in values if str(value).strip())


def _anchors(program: Mapping[str, Any]) -> tuple[str, ...]:
    node_id = str(program.get("node_id") or "")
    profile = point_knowledge_profile(node_id)
    items = program.get("selected_items") or []
    values = [str(program.get("display_name") or "")]
    for item in items:
        if isinstance(item, Mapping):
            values.extend((str(item.get("name") or ""), str(item.get("craft") or "")))
    if profile is not None:
        values.extend((*profile.visible_components, *profile.optional_dimensions))
    return tuple(dict.fromkeys(value.strip() for value in values if len(value.strip()) >= 2))


def _history_keys(history: Any) -> tuple[set[str], set[str]]:
    domains: set[str] = set()
    facts: set[str] = set()
    if not isinstance(history, list):
        return domains, facts
    for record in history:
        if not isinstance(record, Mapping):
            continue
        domain = record.get("topic_type")
        fact = record.get("fact_id")
        if isinstance(domain, str): domains.add(domain)
        if isinstance(fact, str): facts.add(fact)
    return domains, facts


def _candidate_score(entry: Mapping[str, Any], anchors: tuple[str, ...]) -> int:
    haystack = " ".join((_title(entry), str(entry.get("content") or "")))
    hits = sum(1 for anchor in anchors if anchor in haystack)
    # A reviewed point profile may contain a domain phrase rather than the
    # eventual source-card title. One hit is enough; no hit means no expansion.
    return hits * 10 + min(len(entry.get("source_ids") or ()), 3)


def _domain_entry_is_renderable(domain: str, entry: Mapping[str, Any]) -> bool:
    """Keep literary cards inside their per-card quotation permission."""
    if domain != "literary_citation":
        return True
    content = str(entry.get("content") or "")
    return "是否允许逐字引用" in content and "允许" in content and "暂不允许" not in content


def _retrieve_candidates(
    program: Mapping[str, Any],
    rag_search: Callable[[str], str],
) -> tuple[list[DetailCandidate], list[dict[str, str]]]:
    anchors = _anchors(program)
    query_prefix = " ".join(anchors[:12])
    candidates: list[DetailCandidate] = []
    rejected: list[dict[str, str]] = []
    for domain, config in DOMAIN_CONFIG.items():
        try:
            payload = parse_rag_payload(rag_search(f"{query_prefix} {config['query']}"))
        except Exception as exc:
            rejected.append({"topic_type": domain, "reason": f"retrieval_error:{type(exc).__name__}"})
            continue
        for entry in payload.get("evidence", []):
            if not isinstance(entry, dict) or _document(entry) != config["document"]:
                continue
            if not evidence_is_safe_for_domain(domain, entry):
                rejected.append({"topic_type": domain, "reason": "evidence_policy_rejected"})
                continue
            if not _domain_entry_is_renderable(domain, entry):
                rejected.append({"topic_type": domain, "reason": "literary_quote_not_allowed"})
                continue
            score = _candidate_score(entry, anchors)
            # Detail is a guided enrichment surface.  When a point has no
            # literal match in a later knowledge document, retain a reviewed
            # domain card as low-priority broad context rather than ending the
            # visitor turn empty-handed. Exact point matches always outrank it.
            if score <= 0:
                score = 1
                rejected.append({"topic_type": domain, "reason": "broad_reviewed_context"})
            fact_id = evidence_identity(entry)
            candidate_id = hashlib.sha256(f"{domain}|{fact_id}".encode("utf-8")).hexdigest()[:18]
            candidates.append(DetailCandidate(candidate_id, domain, _title(entry), entry, score))
    candidates.sort(key=lambda item: (-item.score, item.candidate_id))
    # Hybrid retrieval can legitimately rank all later-domain documents below
    # the current ornament.  The Markdown corpus is itself curated and carries
    # the same section source IDs, so use it only as a bounded recall backstop
    # when fewer than two distinct dimensions survived retrieval.
    if len({item.domain for item in candidates}) < 2:
        existing = {item.candidate_id for item in candidates}
        for entry in _local_reviewed_entries():
            domain = next(
                (key for key, config in DOMAIN_CONFIG.items() if _document(entry) == config["document"]),
                None,
            )
            if domain is None or not evidence_is_safe_for_domain(domain, entry) or not _domain_entry_is_renderable(domain, entry):
                continue
            fact_id = evidence_identity(entry)
            candidate_id = hashlib.sha256(f"{domain}|{fact_id}".encode("utf-8")).hexdigest()[:18]
            if candidate_id in existing:
                continue
            score = max(_candidate_score(entry, anchors), 1)
            candidates.append(DetailCandidate(candidate_id, domain, _title(entry), entry, score))
            existing.add(candidate_id)
        candidates.sort(key=lambda item: (-item.score, item.candidate_id))
    return candidates, rejected


@lru_cache(maxsize=1)
def _local_reviewed_entries() -> tuple[dict[str, Any], ...]:
    """Read curated source sections only; no unreviewed fallback corpus exists."""
    entries: list[dict[str, Any]] = []
    for chunk in load_knowledge_chunks():
        title = " / ".join(chunk.title_path)
        if any(marker in title for marker in ("证据边界", "来源", "仍需", "使用规则", "没有找到")):
            continue
        entries.append(chunk.to_dict())
    return tuple(entries)


def _choose_locally(
    candidates: list[DetailCandidate],
    history: Any,
    selector: Callable[[str], str] | None,
) -> tuple[DetailCandidate | None, dict[str, Any]]:
    used_domains, used_facts = _history_keys(history)
    fresh = [item for item in candidates if item.domain not in used_domains and evidence_identity(dict(item.evidence)) not in used_facts]
    pool = fresh or [item for item in candidates if evidence_identity(dict(item.evidence)) not in used_facts]
    if not pool:
        return None, {"mode": "none", "reason": "all_eligible_evidence_already_used"}
    if selector is not None:
        selection_input = {
            "instruction": (
                "Choose exactly one candidate for a new Chen Clan Academy detail topic. "
                "Prefer an unvisited topic type and concrete evidence. Do not invent facts. "
                "Return JSON only: {\"candidate_id\": \"...\"}."
            ),
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "topic_type": item.domain,
                    "title": item.title,
                    "evidence_excerpt": str(item.evidence.get("content") or "")[:700],
                }
                for item in pool
            ],
        }
        try:
            raw = selector(json.dumps(selection_input, ensure_ascii=False))
            choice = json.loads(str(raw))
            candidate_id = choice.get("candidate_id") if isinstance(choice, dict) else None
            selected = next((item for item in pool if item.candidate_id == candidate_id), None)
            if selected is not None:
                return selected, {"mode": "model_selection", "pool_size": len(pool), "model_called": True}
            model_reason = "model_selected_unknown_candidate"
        except Exception as exc:
            model_reason = f"model_selection_failed:{type(exc).__name__}"
    else:
        model_reason = "model_selector_unavailable"
    # Weighted random selection is intentionally limited to independently
    # validated candidates. Its ordinal is retained for replay/audit.
    total = sum(max(item.score, 1) for item in pool)
    ticket = secrets.randbelow(total)
    cursor = 0
    chosen = pool[-1]
    for item in pool:
        cursor += max(item.score, 1)
        if ticket < cursor:
            chosen = item
            break
    return chosen, {
        "mode": "weighted_random_fallback", "ticket": ticket, "pool_size": len(pool),
        "model_called": selector is not None, "fallback_reason": model_reason,
    }


def _sentences(entry: Mapping[str, Any], *, limit: int = 3) -> list[str]:
    raw = " ".join(str(entry.get("content") or "").split())
    parts = re.split(r"(?<=[。！？])", raw)
    values: list[str] = []
    for part in parts:
        cleaned = _LABEL_PREFIX.sub("", part.strip()).strip()
        if not cleaned or len(cleaned) < 14 or _SKIP_SENTENCE.search(cleaned):
            continue
        if len(cleaned) > 260:
            cleaned = cleaned[:260].rstrip("，、；：") + "。"
        if cleaned not in values:
            values.append(cleaned)
        if len(values) >= limit:
            break
    return values


def _card_field(entry: Mapping[str, Any], label: str) -> str:
    """Read one reviewed Markdown card field without exposing its metadata labels."""
    content = str(entry.get("content") or "")
    pattern = re.compile(
        rf"(?m)^\s*[-*]\s*(?:\*\*)?{re.escape(label)}(?:\*\*)?[：:]\s*(.+?)\s*$"
    )
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def _public_facts(candidate: DetailCandidate) -> list[str]:
    """Turn structured source cards into visitor prose rather than a catalog dump."""
    if candidate.domain != "literary_citation":
        return _sentences(candidate.evidence, limit=2)

    # Literary cards carry bibliographic checks for the system, but a guide
    # should first explain the story, not recite author or edition metadata.
    work = _card_field(candidate.evidence, "篇名")
    guide = _card_field(candidate.evidence, "导游解释")
    return [fact for fact in (work, guide) if fact][:2]


def _render(candidates: list[DetailCandidate]) -> str | None:
    """Render at least two new factual paragraphs whenever evidence permits."""
    sections: list[str] = []
    for candidate in candidates:
        facts = _public_facts(candidate)
        if not facts:
            continue
        label = DOMAIN_CONFIG[candidate.domain]["label"]
        sections.append(f"{label}\n" + "\n".join(facts))
    # Both selected evidence packages must survive public-sentence filtering.
    # Without this guard a valid first card plus an empty/metadata-only second
    # card would falsely satisfy the two-angle planner contract.
    if len(sections) < 2:
        return None
    # This is a transition, not an explanation of the internal relevance rule.
    return "再换两个角度展开说。\n\n" + "\n\n".join(sections)


def build_detail_expansion(
    program: Mapping[str, Any] | None,
    history: Any,
    rag_search: Callable[[str], str],
    *,
    selector: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Return one checkpoint-safe, evidence-only expansion or fail closed."""
    if not isinstance(program, Mapping) or not program.get("node_id"):
        return {"status": "fallback", "message": LAST_RESORT_MESSAGE, "audit": {"reason": "stop_program_unavailable"}}
    candidates, rejected = _retrieve_candidates(program, rag_search)
    chosen, selection_audit = _choose_locally(candidates, history, selector)
    if chosen is None:
        return {
            "status": "fallback", "message": LAST_RESORT_MESSAGE, "audit": {
                "reason": selection_audit["reason"],
                "candidates": [item.audit_dict() for item in candidates], "rejected": rejected,
            },
        }
    first_record = {
        "topic_type": chosen.domain,
        "fact_id": evidence_identity(dict(chosen.evidence)),
        "candidate_id": chosen.candidate_id,
        "node_id": program.get("node_id"),
        "source_ids": list(chosen.evidence.get("source_ids") or ()),
    }
    # A second choice is deliberately made after treating the first one as
    # used. This produces two different dimensions whenever the evidence pool
    # has them, rather than two paragraphs from a single fixed template.
    secondary, secondary_selection_audit = _choose_locally(
        candidates, [*(history if isinstance(history, list) else []), first_record], selector,
    )
    if secondary is None:
        # The public contract for this action is two substantive additions.
        # Do not silently degrade to one long paragraph when the second
        # evidence dimension cannot be selected.
        return {
            "status": "fallback", "message": LAST_RESORT_MESSAGE, "audit": {
                "reason": "second_detail_dimension_unavailable",
                "selected": [chosen.audit_dict()],
                "candidates": [item.audit_dict() for item in candidates],
                "rejected": rejected,
                "model_called": bool(selection_audit.get("model_called")),
            },
        }
    selected = [chosen, *([secondary] if secondary is not None else [])]
    message = _render(selected)
    if not message:
        return {
            "status": "fallback", "message": LAST_RESORT_MESSAGE, "audit": {
                "reason": "no_safe_public_sentences", "selected": [item.audit_dict() for item in selected],
                "candidates": [item.audit_dict() for item in candidates], "rejected": rejected,
            },
        }
    records = [
        {
            "topic_type": item.domain,
            "fact_id": evidence_identity(dict(item.evidence)),
            "candidate_id": item.candidate_id,
            "node_id": program.get("node_id"),
            "source_ids": list(item.evidence.get("source_ids") or ()),
        }
        for item in selected
    ]
    return {
        "status": "accepted", "message": message,
        "card": {"type": DOMAIN_CONFIG[chosen.domain]["format"], "title": DOMAIN_CONFIG[chosen.domain]["label"]},
        # Retain the singular key for thin callers; the graph commits every
        # record in ``history_records``.
        "history_record": records[0], "history_records": records,
        "audit": {
            "selected": [item.audit_dict() for item in selected],
            "selection": [selection_audit, secondary_selection_audit],
            "candidates": [item.audit_dict() for item in candidates], "rejected": rejected,
            "model_called": bool(selection_audit.get("model_called") or secondary_selection_audit.get("model_called")),
        },
    }
