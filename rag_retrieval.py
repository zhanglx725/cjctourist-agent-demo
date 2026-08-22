"""Persistent Chinese hybrid retrieval for the Chen Clan Academy RAG.

The index is intentionally independent from the agent graph.  Build it after any
knowledge Markdown update, then query it from the Agent's future RAG tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Iterable, Sequence

from rag_ingestion import KNOWLEDGE_DIR, KnowledgeChunk, load_knowledge_chunks


DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
# This is the already-downloaded, evaluation-verified CPU baseline.  Larger
# multilingual rerankers remain opt-in through RAG_RERANKER_MODEL; they are not
# a latency optimisation for this local prototype.
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"
DEFAULT_INDEX_DIR = Path("data/chen_clan_academy/index")
# Four candidates preserve 100% Top-1/Top-3 on the current static evaluation
# set while cutting CPU reranking latency roughly in half versus eight.
DEFAULT_CANDIDATE_LIMIT = 4
DEFAULT_RERANKER_MAX_LENGTH = 256
DEFAULT_RERANKER_BATCH_SIZE = 8
COLLECTION_NAME = "chen_clan_academy_snapshot_v1"
MANIFEST_NAME = "manifest.json"
_TOKEN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")
_NON_EVIDENCE_TITLES = frozenset(
    {
        "RAG 使用规则",
        "RAG 检索与回答规则",
        "RAG 回答规则",
        "来源与核验",
        "待核验项",
        "不进入游客问答的运营公告",
    }
)


@dataclass(frozen=True)
class RetrievedEvidence:
    """Evidence returned to the agent, including enough metadata for citation."""

    chunk_id: str
    content: str
    score: float
    retrieval_methods: tuple[str, ...]
    document: str
    title_path: tuple[str, ...]
    category: str
    source_ids: tuple[str, ...]
    status: str | None
    valid_from: str | None
    valid_to: str | None
    verified_at: str | None

    @classmethod
    def from_chunk(
        cls, chunk: KnowledgeChunk, score: float, methods: Iterable[str]
    ) -> "RetrievedEvidence":
        return cls(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            score=score,
            retrieval_methods=tuple(sorted(set(methods))),
            document=chunk.document,
            title_path=chunk.title_path,
            category=chunk.category,
            source_ids=chunk.source_ids,
            status=chunk.status,
            valid_from=chunk.valid_from,
            valid_to=chunk.valid_to,
            verified_at=chunk.verified_at,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["title_path"] = list(self.title_path)
        data["source_ids"] = list(self.source_ids)
        data["retrieval_methods"] = list(self.retrieval_methods)
        return data


def tokenize(text: str) -> list[str]:
    """Small dependency-free tokenizer for Chinese keyword recall.

    Whole Han runs preserve broad context; overlapping 2–6-character grams retain
    common Chinese proper nouns such as ``百鸟朝凤`` without a separate segmenter.
    """
    tokens: list[str] = []
    for match in _TOKEN.finditer(text.lower()):
        term = match.group(0)
        tokens.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]+", term):
            for width in range(2, min(6, len(term)) + 1):
                tokens.extend(
                    term[index : index + width]
                    for index in range(len(term) - width + 1)
                )
    return tokens


def retrieval_text(chunk: KnowledgeChunk) -> str:
    """Build the searchable representation without altering displayable evidence.

    Titles are essential for exact retrieval of named ornaments, while category and
    source identifiers provide useful disambiguating context.  The original body is
    retained verbatim as the final evidence shown to the model and user.
    """
    return "\n".join(
        part
        for part in (
            # The H1 is a document-wide label (for example every ornament entry
            # shares “陈家祠建筑装饰条目知识库”).  Indexing it in every chunk makes
            # broad questions about 陈家祠 over-match unrelated entries.  The leaf
            # heading is the actual retrieval unit; retain its parent only for H3
            # notices, where it supplies useful notice context.
            f"标题：{' / '.join(chunk.title_path[-2:]) if len(chunk.title_path) > 2 else chunk.title_path[-1]}",
            f"类别：{chunk.category}",
            f"来源：{'、'.join(chunk.source_ids)}" if chunk.source_ids else "",
            chunk.content,
        )
        if part
    )


def is_indexable_evidence(chunk: KnowledgeChunk) -> bool:
    """Keep editorial guidance out of answer evidence while retaining it in Markdown.

    These sections guide ingestion or future operations; they are not visitor-facing
    facts and otherwise become noisy semantic matches for broad questions.
    """
    return chunk.title_path[-1] not in _NON_EVIDENCE_TITLES


def exact_title_matches(
    query: str,
    chunks: Iterable[KnowledgeChunk],
    categories: Sequence[str] | None = None,
) -> list[KnowledgeChunk]:
    """Return unambiguous named-ornament matches without expensive ML inference.

    A three-character minimum avoids treating generic short terms such as ``福`` as
    an exact entity.  Matching the whole title (or its text before a craft suffix)
    naturally returns the paired item and location chunks for names like 百鸟朝凤.
    """
    matches: list[KnowledgeChunk] = []
    for chunk in chunks:
        if categories and chunk.category not in categories:
            continue
        title = chunk.title_path[-1]
        base_title = re.split(r"[（(:：]", title, maxsplit=1)[0].strip()
        if len(base_title) >= 3 and base_title in query:
            matches.append(chunk)
    category_order = {"ornament_item": 0, "ornament_location": 1}
    return sorted(matches, key=lambda chunk: (category_order.get(chunk.category, 2), chunk.chunk_id))


def should_rerank(query: str) -> bool:
    """Decide whether an open or ambiguous question merits cross-encoder cost.

    Exact-title questions already return above.  The remaining default is the
    fast BM25 + dense + RRF route.  Reranking is reserved for questions whose
    answer requires distinguishing similar sections, explaining a source
    discrepancy, or comparing architectural facts.
    """
    normalized = re.sub(r"\s+", "", query)
    complex_markers = (
        "为什么",
        "为何",
        "差异",
        "区别",
        "对比",
        "比较",
        "相比",
        "冲突",
        "来源",
        "依据",
        "哪个",
        "怎么",
        "如何",
        "特点",
        "意义",
        "作用",
        "风格",
    )
    # A broad "陈家祠是什么" query previously needed reranking to select the
    # historical overview instead of the architectural-layout section.
    is_site_identity = "陈家祠" in normalized and "是什么" in normalized
    return is_site_identity or any(marker in normalized for marker in complex_markers)


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]], k: int = 60
) -> dict[str, float]:
    """Fuse rank-only results so vector and keyword scores need no calibration."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + rank)
    return scores


def _lazy_dependencies():
    try:
        import chromadb
        from rank_bm25 import BM25Okapi
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "缺少本地 RAG 依赖。请在虚拟环境运行："
            "pip install -r requirements.txt"
        ) from exc
    return chromadb, BM25Okapi, CrossEncoder, SentenceTransformer


def _chunk_metadata(chunk: KnowledgeChunk) -> dict[str, str]:
    """Chroma metadata accepts scalar values only; encode multi-value fields."""
    return {
        "document": chunk.document,
        "title_path": json.dumps(chunk.title_path, ensure_ascii=False),
        "category": chunk.category,
        "source_ids": json.dumps(chunk.source_ids, ensure_ascii=False),
        "status": chunk.status or "",
        "valid_from": chunk.valid_from or "",
        "valid_to": chunk.valid_to or "",
        "verified_at": chunk.verified_at or "",
    }


class ChenClanHybridRetriever:
    """Build and query a local snapshot index with vector and BM25 recall."""

    def __init__(
        self,
        index_dir: Path = DEFAULT_INDEX_DIR,
        model_name: str | None = None,
    ):
        self.index_dir = Path(index_dir)
        self.model_name = model_name or os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_MODEL)
        self.reranker_model_name = os.getenv("RAG_RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
        self.reranker_max_length = int(
            os.getenv("RAG_RERANKER_MAX_LENGTH", str(DEFAULT_RERANKER_MAX_LENGTH))
        )
        self.reranker_batch_size = int(
            os.getenv("RAG_RERANKER_BATCH_SIZE", str(DEFAULT_RERANKER_BATCH_SIZE))
        )
        self.candidate_limit = int(
            os.getenv("RAG_CANDIDATE_LIMIT", str(DEFAULT_CANDIDATE_LIMIT))
        )
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._bm25 = None
        self._model = None
        self._reranker = None
        self._collection = None
        # The demo warms models in the background. Guard lazy construction so
        # a very early visitor request never creates a duplicate transformer.
        self._model_lock = threading.Lock()
        self._reranker_lock = threading.Lock()

    @property
    def manifest_path(self) -> Path:
        return self.index_dir / MANIFEST_NAME

    def _model_instance(self):
        with self._model_lock:
            if self._model is None:
                _, _, _, SentenceTransformer = _lazy_dependencies()
                self._model = SentenceTransformer(self.model_name)
        return self._model

    def _reranker_instance(self):
        with self._reranker_lock:
            if self._reranker is None:
                _, _, CrossEncoder, _ = _lazy_dependencies()
                self._reranker = CrossEncoder(
                    self.reranker_model_name, max_length=self.reranker_max_length
                )
        return self._reranker

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model_instance().encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.tolist()

    def build(self, chunks: list[KnowledgeChunk] | None = None) -> int:
        """Create a fresh persistent snapshot index from curated knowledge chunks."""
        chromadb, BM25Okapi, _, _ = _lazy_dependencies()
        chunks = chunks or load_knowledge_chunks(KNOWLEDGE_DIR)
        chunks = [chunk for chunk in chunks if is_indexable_evidence(chunk)]
        if not chunks:
            raise ValueError("没有可索引的知识块。")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.index_dir))
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self._collection = client.create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
        )
        self._chunks = {chunk.chunk_id: chunk for chunk in chunks}
        searchable_texts = [retrieval_text(chunk) for chunk in chunks]
        embeddings = self._embed(searchable_texts)
        self._collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=searchable_texts,
            metadatas=[_chunk_metadata(chunk) for chunk in chunks],
            embeddings=embeddings,
        )
        self._bm25 = BM25Okapi([tokenize(retrieval_text(chunk)) for chunk in chunks])
        self._write_manifest(chunks)
        return len(chunks)

    def _write_manifest(self, chunks: list[KnowledgeChunk]) -> None:
        payload = {
            "schema_version": 1,
            "collection": COLLECTION_NAME,
            "embedding_model": self.model_name,
            "built_at": datetime.now(UTC).isoformat(),
            "chunks": [chunk.to_dict() for chunk in chunks],
        }
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> int:
        """Open the persisted vector collection and rebuild the small BM25 memory index."""
        if not self.manifest_path.exists():
            raise FileNotFoundError("未找到索引清单；请先执行 build_index.py。")
        chromadb, BM25Okapi, _, _ = _lazy_dependencies()
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if payload.get("embedding_model") != self.model_name:
            raise RuntimeError("embedding 模型与索引不一致；请使用相同模型或重新构建索引。")
        chunks = [
            KnowledgeChunk(
                **{
                    **item,
                    "title_path": tuple(item["title_path"]),
                    "source_ids": tuple(item["source_ids"]),
                }
            )
            for item in payload["chunks"]
        ]
        self._chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self._bm25 = BM25Okapi([tokenize(retrieval_text(chunk)) for chunk in chunks])
        client = chromadb.PersistentClient(path=str(self.index_dir))
        self._collection = client.get_collection(COLLECTION_NAME)
        return len(chunks)

    def warm_up(self) -> None:
        """Load both ML models during server startup, outside a visitor request."""
        if self._collection is None or self._bm25 is None:
            self.load()
        self._embed(["陈家祠导览预热"])
        self._reranker_instance().predict(
            [("陈家祠导览预热", "陈家祠本地知识库预热")],
            batch_size=1,
            show_progress_bar=False,
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        candidate_limit: int | None = None,
        rerank: bool | None = None,
        categories: Sequence[str] | None = None,
    ) -> list[RetrievedEvidence]:
        """Return evidence after RRF and optional/automatic cross-encoder ranking.

        ``True`` forces reranking for benchmark comparisons; ``False`` disables
        it; ``None`` (the production default) applies :func:`should_rerank`.
        """
        if not query.strip():
            return []
        if self._collection is None or self._bm25 is None:
            self.load()
        assert self._collection is not None and self._bm25 is not None
        direct_matches = exact_title_matches(query, self._chunks.values(), categories)
        if direct_matches:
            return [
                RetrievedEvidence.from_chunk(chunk, 1.0, ("exact_title",))
                for chunk in direct_matches[:limit]
            ]
        use_reranker = should_rerank(query) if rerank is None else rerank
        eligible_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if not categories or chunk.category in categories
        ]
        if not eligible_ids:
            return []
        candidate_limit = candidate_limit or self.candidate_limit
        candidate_limit = min(max(limit, candidate_limit), len(eligible_ids))
        where = {"category": {"$in": list(categories)}} if categories else None
        vector = self._collection.query(
            query_embeddings=self._embed([query]),
            n_results=candidate_limit,
            where=where,
            include=[],
        )
        semantic_ids = vector["ids"][0]
        keyword_scores = self._bm25.get_scores(tokenize(query))
        keyword_ids = [
            chunk_id
            for chunk_id, _ in sorted(
                (
                    (chunk_id, score)
                    for chunk_id, score in zip(self._chunks, keyword_scores)
                    if chunk_id in eligible_ids
                ),
                key=lambda item: item[1],
                reverse=True,
            )[:candidate_limit]
        ]
        fused = reciprocal_rank_fusion([semantic_ids, keyword_ids])
        methods = {
            chunk_id: tuple(
                method
                for method, ranked in (("semantic", semantic_ids), ("keyword", keyword_ids))
                if chunk_id in ranked
            )
            for chunk_id in fused
        }
        candidates = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:candidate_limit]
        if use_reranker:
            pairs = [(query, retrieval_text(self._chunks[chunk_id])) for chunk_id, _ in candidates]
            rerank_scores = self._reranker_instance().predict(
                pairs,
                batch_size=self.reranker_batch_size,
                show_progress_bar=False,
            )
            candidates = sorted(
                zip((chunk_id for chunk_id, _ in candidates), rerank_scores),
                key=lambda item: float(item[1]),
                reverse=True,
            )
        return [
            RetrievedEvidence.from_chunk(
                self._chunks[chunk_id],
                float(score),
                (*methods[chunk_id], "reranker") if use_reranker else methods[chunk_id],
            )
            for chunk_id, score in candidates[:limit]
        ]
