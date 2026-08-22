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

    def test_people_sections_are_ingested_with_section_sources(self):
        people = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "10_people_builders_craftspeople.md"
            and chunk.title_path[-1] == "二、文物保护、研究与工艺传承人物"
        )
        self.assertEqual(people.category, "history_architecture")
        self.assertEqual(people.source_ids, ("S13", "S15", "S16", "S17"))

    def test_conservation_sections_distinguish_precise_evidence_sources(self):
        conservation = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "11_architectural_conservation.md"
            and chunk.title_path[-1] == "五、陶塑、石雕、砖雕和彩绘：已有巡查，专项病害资料不足"
        )
        self.assertEqual(conservation.category, "history_architecture")
        self.assertEqual(conservation.source_ids, ("S19",))
        self.assertIn("本轮检索没有找到公开的陈家祠专项报告", conservation.content)
        self.assertIn("不得将其他地区彩画修复原则直接写成陈家祠工程事实", conservation.content)

    def test_craft_process_sections_keep_scope_and_precise_sources(self):
        pottery = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "12_craft_process_and_transmission.md"
            and chunk.title_path[-1] == "三、陶塑瓦脊：分件烧制，再运输和安装"
        )
        self.assertEqual(pottery.category, "ornament_craft")
        self.assertEqual(pottery.source_ids, ("S14", "S30", "S32", "S36"))
        self.assertIn("不得说成陈家祠每条瓦脊", pottery.content)
        self.assertIn("包装运到工地", pottery.content)

    def test_literary_cards_separate_direct_and_atmospheric_quotes(self):
        direct = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "13_literary_citation_cards.md"
            and chunk.title_path[-1] == "二、引用卡 A01：九如图与《诗经·小雅·天保》"
        )
        atmospheric = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "13_literary_citation_cards.md"
            and chunk.title_path[-1] == "九、引用卡 C01：借《诗经·斯干》形容屋脊"
        )
        disputed = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "13_literary_citation_cards.md"
            and chunk.title_path[-1] == "六、引用卡 A05：夜游赤壁的来源冲突"
        )
        self.assertEqual(direct.category, "literary_citation")
        self.assertEqual(direct.source_ids, ("S11", "S38"))
        self.assertIn("不等于《诗经》原文描写九鱼图", direct.content)
        self.assertIn("并非描写陈家祠", atmospheric.content)
        self.assertIn("暂不允许", disputed.content)

    def test_student_history_keeps_commemoration_separate_from_residence(self):
        flagstones = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "14_students_examinations_and_education.md"
            and chunk.title_path[-1] == "四、旗杆夹石：四位人物与两种教育制度"
        )
        rules = next(
            chunk
            for chunk in self.chunks
            if chunk.document == "14_students_examinations_and_education.md"
            and chunk.title_path[-1] == "二、《议建陈氏书院章程》：制度设想不等于执行记录"
        )
        self.assertEqual(flagstones.category, "history_architecture")
        self.assertEqual(flagstones.source_ids, ("S12",))
        self.assertIn("不证明他们曾在陈氏书院住宿", flagstones.content)
        self.assertIn("尚不能确认", rules.content)
        self.assertIn("膏火是否实际发放", rules.content)


if __name__ == "__main__":
    unittest.main()
