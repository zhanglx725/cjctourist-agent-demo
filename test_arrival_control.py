from __future__ import annotations

import unittest

from arrival_control import is_safe_arrival_report_text, looks_like_arrival_control


class ArrivalControlTests(unittest.TestCase):
    def test_structural_arrival_reports_are_safe(self):
        for text in ("我已经抵达这里了", "我人到了", "我终于抵达啦", "终于走到月台了"):
            with self.subTest(text=text):
                self.assertTrue(looks_like_arrival_control(text))
                self.assertTrue(is_safe_arrival_report_text(text))

    def test_static_location_questions_do_not_match_the_arrival_guard(self):
        for text in ("我在月台能看到什么？", "月台能看到什么？"):
            with self.subTest(text=text):
                self.assertFalse(looks_like_arrival_control(text))
                self.assertFalse(is_safe_arrival_report_text(text))

    def test_non_arrival_location_controls_are_never_safe_reports(self):
        for text in (
            "我想去月台", "我还在去月台的路上", "我快到月台了", "我还没到月台",
            "如果我到了月台怎么办", "我是不是到了月台", "朋友已经到月台了",
        ):
            with self.subTest(text=text):
                self.assertTrue(looks_like_arrival_control(text))
                self.assertFalse(is_safe_arrival_report_text(text))

    def test_next_stop_question_is_not_a_destination_intent(self):
        self.assertFalse(looks_like_arrival_control("接下来去哪"))


if __name__ == "__main__":
    unittest.main()
