"""Regression checks for the bilingual glossary data contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


GLOSSARY_PATH = (
    Path(__file__).parent
    / "data"
    / "chen_clan_academy"
    / "glossary"
    / "glossary_zh_en_v0.yaml"
)


class GlossaryDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = GLOSSARY_PATH.read_text(encoding="utf-8")
        cls.entries = re.findall(r"^  - term_id: ([a-z0-9_]+)$", cls.text, re.MULTILINE)

    def test_term_ids_are_unique_and_first_batch_is_substantial(self) -> None:
        self.assertGreaterEqual(len(self.entries), 30)
        self.assertEqual(len(self.entries), len(set(self.entries)))

    def test_every_term_has_translation_status_sources_and_verification_date(self) -> None:
        blocks = re.split(r"(?=^  - term_id:)", self.text, flags=re.MULTILINE)
        for block in blocks:
            if not block.startswith("  - term_id:"):
                continue
            self.assertRegex(block, r"\n    zh: .+")
            self.assertRegex(block, r"\n    en: .+")
            self.assertRegex(block, r"\n    domain: [a-z_]+\n")
            self.assertRegex(block, r"\n    translation_status: (draft|reviewed)\n")
            self.assertRegex(block, r"\n    source_ids: \[S\d+(?:, S\d+)*\]\n")
            self.assertRegex(block, r"\n    verified_at: \d{4}-\d{2}-\d{2}\n")

    def test_seven_craft_categories_are_present(self) -> None:
        expected = {
            "陶塑",
            "灰塑",
            "木雕",
            "石雕",
            "砖雕",
            "铜铁铸",
            "彩绘",
        }
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_route_stop_names_do_not_enter_the_research_glossary(self) -> None:
        route_stop_names = {
            "首进正厅",
            "月台",
            "聚贤堂",
            "后进正厅",
            "东厅",
            "西厅",
        }
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertFalse(route_stop_names & found)

    def test_materials_and_processes_needed_for_craft_questions_are_present(self) -> None:
        expected = {
            "草筋灰",
            "纸筋灰",
            "贴塑",
            "捏塑",
            "模制",
            "水磨青砖",
            "阴刻",
            "透雕",
            "圆雕",
            "线刻",
        }
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_core_craft_materials_are_present(self) -> None:
        expected = {"石灰", "陶泥", "色釉", "花岗岩", "青砖", "通雕"}
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_research_relevant_components_and_conservation_terms_are_present(self) -> None:
        expected = {"山墙", "柱础", "抱鼓石", "白蚁监测预警与诱杀", "建筑动态安全监测"}
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_clan_history_and_heritage_terms_are_present(self) -> None:
        expected = {"宗族", "题捐牌位", "祭祀", "科举", "建祠公所", "全国重点文物保护单位"}
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_research_component_terms_are_present(self) -> None:
        expected = {"坨墩", "檐板", "花罩", "勾门", "垂带", "墀头", "挂线砖雕", "石华表", "石五供"}
        found = set(re.findall(r"^    zh: (.+)$", self.text, re.MULTILINE))
        self.assertTrue(expected.issubset(found))

    def test_retrieval_rule_file_is_present(self) -> None:
        rules_path = GLOSSARY_PATH.with_name("glossary_retrieval_rules_v0.yaml")
        rules = rules_path.read_text(encoding="utf-8")
        self.assertIn("domain_rules:", rules)
        self.assertIn("term_overrides:", rules)
        self.assertIn("term_quetti_bracket:", rules)

    def test_every_current_domain_has_a_retrieval_rule(self) -> None:
        rules_path = GLOSSARY_PATH.with_name("glossary_retrieval_rules_v0.yaml")
        rules = rules_path.read_text(encoding="utf-8")
        domains = set(re.findall(r"^    domain: ([a-z_]+)$", self.text, re.MULTILINE))
        declared_domains = set(re.findall(r"^  ([a-z_]+):$", rules, re.MULTILINE))
        self.assertTrue(domains.issubset(declared_domains))


if __name__ == "__main__":
    unittest.main()
