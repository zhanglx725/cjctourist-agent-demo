import unittest

from visitor_localization import localize_visitor_text, target_language_name


class VisitorLocalizationTests(unittest.TestCase):
    def test_before_language_outputs_chinese_then_english(self):
        result = localize_visitor_text("路线已生成。", None, lambda _text, target: f"Route ready. ({target})")
        self.assertEqual(result.public_text, "路线已生成。\n\nRoute ready. (English)")
        self.assertEqual(result.target_language, "zh+en")

    def test_known_bilingual_prompt_does_not_call_api(self):
        called = []
        result = localize_visitor_text(
            "请选择语言。\n\nPlease select a language.", None,
            lambda *_args: called.append(True) or "bad",
            already_bilingual=True,
        )
        self.assertEqual(called, [])
        self.assertEqual(result.status, "already_bilingual")

    def test_before_language_api_failure_still_has_honest_bilingual_output(self):
        result = localize_visitor_text("路线已生成。", None, lambda *_args: "")
        self.assertIn("路线已生成", result.public_text)
        self.assertIn("translation is temporarily unavailable", result.public_text)
        self.assertEqual(result.status, "translation_unavailable")

    def test_selected_language_returns_only_translation(self):
        result = localize_visitor_text("请选择模式。", "ko", lambda _text, target: f"모드를 선택하세요. [{target}]")
        self.assertNotIn("请选择模式", result.public_text)
        self.assertIn("모드를 선택하세요", result.public_text)

    def test_chinese_selection_does_not_call_api_for_chinese_source(self):
        called = []
        result = localize_visitor_text("请选择模式。", "zh", lambda *_args: called.append(True) or "bad")
        self.assertEqual(called, [])
        self.assertEqual(result.public_text, "请选择模式。")

    def test_translation_must_preserve_arabic_numbers(self):
        result = localize_visitor_text("路线约30分钟。", "en", lambda *_args: "The route is ready.")
        self.assertEqual(result.status, "translation_unavailable")
        self.assertEqual(result.public_text, "路线约30分钟。")

    def test_arbitrary_language_name_is_preserved_as_target(self):
        self.assertEqual(target_language_name("泰语"), "泰语")


if __name__ == "__main__":
    unittest.main()
