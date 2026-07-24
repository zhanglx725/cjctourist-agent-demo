"""Static retrieval evaluation derived from FAQ intent coverage.

The expected targets are source documents/titles, not FAQ answer text.  This keeps
the evaluation set isolated from the retrieval corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse

from rag_retrieval import ChenClanHybridRetriever, RetrievedEvidence


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    query: str
    expected_document: str
    expected_title_contains: tuple[str, ...]
    categories: tuple[str, ...]


STATIC_CASES = (
    RetrievalEvaluationCase(
        "history_identity", "陈家祠是什么？", "02_history_architecture.md", ("历史沿革",), ("history_architecture",)
    ),
    RetrievalEvaluationCase(
        # Both sections contain the relevant, source-grounded explanation: one
        # gives the institution's historical function, the other its context.
        "academy_name", "为什么陈家祠又叫陈氏书院？", "02_history_architecture.md", ("历史沿革", "文化解释"), ("history_architecture",)
    ),
    RetrievalEvaluationCase(
        "completion_conflict", "陈家祠什么时候建成？", "02_history_architecture.md", ("历史沿革",), ("history_architecture",)
    ),
    RetrievalEvaluationCase(
        "building_layout", "陈家祠的建筑布局有什么特点？", "02_history_architecture.md", ("建筑格局",), ("history_architecture",)
    ),
    RetrievalEvaluationCase(
        "moon_platform", "月台有哪些值得看的石雕？", "07_ornament_crafts.md", ("石雕",), ("ornament_craft",)
    ),
    RetrievalEvaluationCase(
        "plaster_craft", "灰塑是什么？", "07_ornament_crafts.md", ("灰塑",), ("ornament_craft",)
    ),
    RetrievalEvaluationCase(
        "bird_phoenix", "百鸟朝凤是什么装饰？", "08_ornament_items.md", ("百鸟朝凤",), ("ornament_item", "ornament_location"),
    ),
    RetrievalEvaluationCase(
        "liangshan_story", "梁山聚义讲的是什么？", "08_ornament_items.md", ("梁山聚义",), ("ornament_item", "ornament_location"),
    ),
)


def is_expected(case: RetrievalEvaluationCase, evidence: RetrievedEvidence) -> bool:
    return (
        evidence.document == case.expected_document
        and any(title in evidence.title_path[-1] for title in case.expected_title_contains)
    )


def evaluate(
    retriever: ChenClanHybridRetriever,
    rerank: bool | None = None,
    candidate_limit: int | None = None,
) -> tuple[list[dict], dict[str, float]]:
    results: list[dict] = []
    for case in STATIC_CASES:
        evidence = retriever.search(
            case.query,
            limit=3,
            categories=case.categories,
            rerank=rerank,
            candidate_limit=candidate_limit,
        )
        ranks = [rank for rank, item in enumerate(evidence, start=1) if is_expected(case, item)]
        results.append(
            {
                "case": case,
                "evidence": evidence,
                "top_1": 1 in ranks,
                "top_3": bool(ranks),
            }
        )
    total = len(results)
    metrics = {
        "top_1_accuracy": sum(result["top_1"] for result in results) / total,
        "top_3_recall": sum(result["top_3"] for result in results) / total,
    }
    return results, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate static RAG retrieval quality.")
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Evaluate BM25 + dense retrieval + RRF without the cross-encoder reranker.",
    )
    parser.add_argument(
        "--force-rerank",
        action="store_true",
        help="Force the cross-encoder for every non-exact-title query.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Override the RRF candidate pool size for a retrieval A/B test.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the top-three pre/post-ranking evidence titles, scores and methods.",
    )
    args = parser.parse_args()
    if args.no_rerank and args.force_rerank:
        parser.error("--no-rerank and --force-rerank cannot be used together.")
    retriever = ChenClanHybridRetriever()
    retriever.load()
    rerank_mode = False if args.no_rerank else True if args.force_rerank else None
    if args.candidate_limit is not None and args.candidate_limit < 3:
        parser.error("--candidate-limit must be at least 3 because evaluation uses Top-3 recall.")
    results, metrics = evaluate(
        retriever, rerank=rerank_mode, candidate_limit=args.candidate_limit
    )
    mode_label = (
        "BM25 + dense + RRF"
        if rerank_mode is False
        else "BM25 + dense + RRF + reranker (forced)"
        if rerank_mode is True
        else "BM25 + dense + RRF + conditional reranker"
    )
    pool_label = args.candidate_limit or retriever.candidate_limit
    print(f"Mode: {mode_label} | candidate_pool={pool_label}")
    for result in results:
        case = result["case"]
        first = result["evidence"][0] if result["evidence"] else None
        found = "PASS" if result["top_3"] else "FAIL"
        first_title = " > ".join(first.title_path) if first else "无结果"
        print(f"{found} {case.case_id}: Top-1={result['top_1']} | {first_title}")
        if args.verbose:
            for rank, evidence in enumerate(result["evidence"], start=1):
                print(
                    f"  {rank}. score={evidence.score:.6f}"
                    f" | {' > '.join(evidence.title_path)}"
                    f" | {','.join(evidence.retrieval_methods)}"
                )
    print(f"\nTop-1 accuracy: {metrics['top_1_accuracy']:.1%}")
    print(f"Top-3 recall: {metrics['top_3_recall']:.1%}")
