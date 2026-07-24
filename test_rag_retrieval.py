"""Dependency-free tests for hybrid retrieval helpers."""

import unittest

from rag_ingestion import KnowledgeChunk, load_knowledge_chunks
from rag_retrieval import (
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_RERANKER_BATCH_SIZE,
    DEFAULT_RERANKER_MAX_LENGTH,
    DEFAULT_RERANKER_MODEL,
    exact_title_matches,
    is_indexable_evidence,
    reciprocal_rank_fusion,
    retrieval_text,
    should_rerank,
    tokenize,
)


class HybridRetrievalHelperTests(unittest.TestCase):
    def test_tokenizer_keeps_exact_chinese_proper_noun(self):
        tokens = tokenize("百鸟朝凤的灰塑在哪里？")
        self.assertIn("百鸟朝凤", tokens)
        self.assertIn("百鸟", tokens)

    def test_rrf_rewards_agreement_between_retrievers(self):
        scores = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
        self.assertGreater(scores["b"], scores["a"])
        self.assertGreater(scores["b"], scores["c"])

    def test_retrieval_text_contains_title_category_and_body(self):
        chunk = KnowledgeChunk(
            chunk_id="test:0001",
            content="凤凰是吉祥题材。",
            document="08_ornament_items.md",
            title_path=("陈家祠建筑装饰条目知识库", "百鸟朝凤"),
            category="ornament_item",
            source_ids=("S11",),
        )
        text = retrieval_text(chunk)
        self.assertIn("百鸟朝凤", text)
        self.assertNotIn("陈家祠建筑装饰条目知识库", text)
        self.assertIn("ornament_item", text)
        self.assertIn("凤凰是吉祥题材", text)

    def test_editorial_rag_rules_are_not_indexable_evidence(self):
        chunk = KnowledgeChunk(
            chunk_id="test:0002",
            content="这是给研发人员的规则。",
            document="07_ornament_crafts.md",
            title_path=("陈家祠建筑装饰工艺总览", "RAG 检索与回答规则"),
            category="ornament_craft",
            source_ids=("S10",),
        )
        self.assertFalse(is_indexable_evidence(chunk))

    def test_named_ornament_uses_exact_title_fast_path(self):
        chunks = load_knowledge_chunks()
        matches = exact_title_matches("百鸟朝凤是什么装饰？", chunks)
        self.assertEqual([chunk.category for chunk in matches], ["ornament_item", "ornament_location"])
        self.assertEqual(DEFAULT_CANDIDATE_LIMIT, 4)

    def test_cpu_reranker_defaults_are_bounded(self):
        self.assertEqual(DEFAULT_RERANKER_MAX_LENGTH, 256)
        self.assertEqual(DEFAULT_RERANKER_BATCH_SIZE, 8)
        self.assertEqual(DEFAULT_RERANKER_MODEL, "BAAI/bge-reranker-base")

    def test_candidate_pool_default_is_larger_than_requested_top_three(self):
        self.assertGreater(DEFAULT_CANDIDATE_LIMIT, 3)

    def test_conditional_reranker_targets_ambiguous_questions(self):
        self.assertTrue(should_rerank("陈家祠是什么？"))
        self.assertTrue(should_rerank("陈家祠和其他祠堂有什么区别？"))
        self.assertFalse(should_rerank("陈家祠什么时候建成？"))
        self.assertFalse(should_rerank("灰塑是什么？"))


if __name__ == "__main__":
    unittest.main()
