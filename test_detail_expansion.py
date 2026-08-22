import json
import unittest

from detail_expansion import build_detail_expansion


def _entry(document: str, title: str, content: str) -> dict:
    return {
        "document": document,
        "title_path": [title],
        "content": content,
        "source_ids": ["S-test"],
        "chunk_id": f"test-{document}-{title}",
    }


class DetailExpansionTests(unittest.TestCase):
    program = {
        "node_id": "stop_front_courtyard_center",
        "display_name": "前院中部",
        "selected_items": [{"name": "独角狮", "craft": "灰塑"}],
    }

    def _rag(self, query: str) -> str:
        evidence = [
            _entry(
                "10_people_builders_craftspeople.md", "灰塑传承人",
                "馆方资料和公开采访记载邵成村参与过陈家祠灰塑维护，并长期从事传统工艺传承。",
            ),
            _entry(
                "11_architectural_conservation.md", "独角狮保护案例",
                "馆方公开报道记载独角狮维护中使用热成像和近景摄影记录内部结构。该项目发生在2023年后的第八次灰塑维护期间。",
            ),
            _entry(
                "12_craft_process_and_transmission.md", "灰塑制作过程",
                "公开采访记载灰塑可用草筋灰建立体量，再用纸筋灰塑出细节。邵成村曾参与陈家祠灰塑维护。",
            ),
            _entry(
                "14_students_examinations_and_education.md", "旗杆夹石与科举",
                "馆方资料记载陈氏书院曾为参与集资宗族子弟进广州应考或办事提供临时落脚处。旗杆夹石保留了科举功名的公共记忆。",
            ),
            _entry(
                "09_ornament_locations.md", "独角狮位置",
                "独角狮摆放在建筑山墙垂脊前沿。",
            ),
        ]
        return json.dumps({"evidence": evidence}, ensure_ascii=False)

    def test_same_stop_uses_a_new_topic_before_reusing_one(self):
        first = build_detail_expansion(self.program, [], self._rag, selector=None)
        self.assertEqual(first["status"], "accepted")
        self.assertEqual(len(first["history_records"]), 2)
        second = build_detail_expansion(
            self.program, first["history_records"], self._rag, selector=None,
        )
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(len(second["history_records"]), 2)
        self.assertTrue(
            {item["topic_type"] for item in first["history_records"]}.isdisjoint(
                {item["topic_type"] for item in second["history_records"]}
            )
        )

    def test_location_index_is_not_an_expansion_candidate(self):
        result = build_detail_expansion(self.program, [], self._rag, selector=None)
        documents = {
            candidate["document"] for candidate in result["audit"]["candidates"]
        }
        self.assertNotIn("09_ornament_locations.md", documents)

    def test_model_may_choose_only_a_verified_candidate(self):
        def selector(raw: str) -> str:
            candidates = json.loads(raw)["candidates"]
            return json.dumps({"candidate_id": candidates[-1]["candidate_id"]})

        result = build_detail_expansion(self.program, [], self._rag, selector=selector)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["audit"]["selection"][0]["mode"], "model_selection")
        self.assertTrue(result["audit"]["model_called"])

    def test_literary_card_without_quote_permission_is_rejected(self):
        def rag(_: str) -> str:
            entry = _entry(
                "13_literary_citation_cards.md", "独角狮文学卡",
                "原文：某句。作者：某人。篇名：某篇。版本或来源：S。对应装饰或点位：独角狮。是否允许逐字引用：暂不允许。是否为直接相关：是。",
            )
            return json.dumps({"evidence": [entry]}, ensure_ascii=False)

        result = build_detail_expansion(self.program, [], rag, selector=None)
        self.assertEqual(result["status"], "fallback")
        self.assertIn("保护与修缮", result["message"])
        self.assertIn("制作与传承", result["message"])
        reasons = {item["reason"] for item in result["audit"]["rejected"]}
        self.assertIn("literary_quote_not_allowed", reasons)

    def test_empty_second_card_never_becomes_a_one_angle_reply(self):
        def rag(_: str) -> str:
            evidence = [
                _entry(
                    "11_architectural_conservation.md", "独角狮保护案例",
                    "馆方公开报道记载独角狮维护中使用热成像和近景摄影记录内部结构。",
                ),
                _entry(
                    "12_craft_process_and_transmission.md", "灰塑制作过程",
                    "材料：灰塑。",
                ),
            ]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        result = build_detail_expansion(self.program, [], rag, selector=None)
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["audit"]["reason"], "no_safe_public_sentences")
        self.assertIn("保护与修缮", result["message"])
        self.assertIn("制作与传承", result["message"])

    def test_literary_card_explains_the_story_not_its_bibliography(self):
        def rag(_: str) -> str:
            evidence = [
                _entry(
                    "13_literary_citation_cards.md", "古城会",
                    "- **原文**：今日君臣重聚义，正如龙虎会风云。\n"
                    "- **作者**：小说通常署罗贯中。\n"
                    "- **篇名**：《三国演义》第二十八回；通行回目包含“会古城主臣聚义”。\n"
                    "- **导游解释**：张飞从怀疑到确认关羽忠义；蔡阳追兵推动了以行动释疑的冲突。\n"
                    "- **是否允许逐字引用**：允许。",
                ),
                _entry(
                    "12_craft_process_and_transmission.md", "灰塑制作过程",
                    "公开采访记载灰塑可用草筋灰建立体量，再用纸筋灰塑出细节。",
                ),
            ]
            return json.dumps({"evidence": evidence}, ensure_ascii=False)

        result = build_detail_expansion(self.program, [], rag, selector=None)
        self.assertEqual(result["status"], "accepted")
        self.assertIn("《三国演义》第二十八回", result["message"])
        self.assertIn("张飞从怀疑到确认关羽忠义", result["message"])
        self.assertNotIn("罗贯中", result["message"])


if __name__ == "__main__":
    unittest.main()
