"""Small, repeatable latency benchmark for the local Chen Clan Academy RAG.

Run this in the activated virtual environment after building the index.  The
first measured search includes lazy model initialisation; the second measures
the same request with models already resident in the process.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import time

from rag_retrieval import ChenClanHybridRetriever, should_rerank


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    query: str


CASES = (
    BenchmarkCase("exact_title_fast_path", "百鸟朝凤是什么装饰？"),
    BenchmarkCase("plain_fact_rrf", "陈家祠什么时候建成？"),
    BenchmarkCase("ambiguous_identity_rerank", "陈家祠是什么？"),
    BenchmarkCase("comparison_rerank", "陈家祠的建筑布局有什么特点？"),
)


def run_once(
    retriever: ChenClanHybridRetriever, query: str, candidate_limit: int | None = None
) -> tuple[float, str]:
    started = time.perf_counter()
    evidence = retriever.search(query, limit=3, candidate_limit=candidate_limit)
    elapsed = time.perf_counter() - started
    methods = ",".join(evidence[0].retrieval_methods) if evidence else "no_result"
    return elapsed, methods


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark local RAG latency by retrieval path.")
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Override the RRF candidate pool size; use for latency/quality A/B tests.",
    )
    args = parser.parse_args()
    if args.candidate_limit is not None and args.candidate_limit < 3:
        parser.error("--candidate-limit must be at least 3.")
    retriever = ChenClanHybridRetriever()
    loaded = retriever.load()
    print(f"Loaded {loaded} indexable chunks.")
    pool_label = args.candidate_limit or retriever.candidate_limit
    print(f"Candidate pool: {pool_label}")
    print("First = lazy model loading where needed; warm = same process, same query.\n")
    for case in CASES:
        first_seconds, methods = run_once(retriever, case.query, args.candidate_limit)
        warm_seconds, warm_methods = run_once(retriever, case.query, args.candidate_limit)
        print(
            f"{case.name}: conditional_rerank={should_rerank(case.query)} "
            f"| first={first_seconds:.2f}s | warm={warm_seconds:.2f}s "
            f"| methods={warm_methods or methods}"
        )


if __name__ == "__main__":
    main()
