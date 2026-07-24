"""Regression tests for Markdown chunking and its RAG evidence metadata."""

import unittest

from rag_ingestion import load_knowledge_chunks


class KnowledgeIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = load_knowledge_chunks()

    def test_only_curated_knowledge_is_loaded(self):
        self.assertGreater(len(self.chunks), 100)
        self.assertTrue(all("evaluation" not in chunk.document for chunk in self.chunks))
        self.assertTrue(all("raw" not in chunk.document for chunk in self.chunks))

    def test_every_ornament_is_a_standalone_h2_chunk(self):
        ornaments = [chunk for chunk in self.chunks if chunk.category == "ornament_item"]
        self.assertGreaterEqual(len(ornaments), 100)
        self.assertTrue(all(len(chunk.title_path) == 2 for chunk in ornaments))
        self.assertTrue(all("## " not in chunk.content for chunk in ornaments))

    def test_same_name_different_crafts_remain_distinguishable(self):
        matches = [chunk for chunk in self.chunks if chunk.title_path[-1] == "梁山聚义"]
        self.assertEqual({chunk.category for chunk in matches}, {"ornament_item"})
        location_matches = [chunk for chunk in self.chunks if "梁山聚义" in chunk.title_path[-1]]
        self.assertGreaterEqual(len(location_matches), 2)
        self.assertTrue(all(chunk.source_ids for chunk in location_matches))

    def test_expired_notices_keep_status_and_dates(self):
        chunk = next(chunk for chunk in self.chunks if "马到功成" in chunk.title_path[-1])
        self.assertEqual(chunk.status, "已过期")
        self.assertEqual(chunk.valid_from, "2026-02-13")
        self.assertEqual(chunk.valid_to, "2026-06-22")

    def test_history_sections_have_precise_source_ids(self):
        history = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "02_history_architecture.md" and chunk.title_path[-1] == "历史沿革"
        )
        self.assertEqual(history.source_ids, ("S02", "S04"))


if __name__ == "__main__":
    unittest.main()
