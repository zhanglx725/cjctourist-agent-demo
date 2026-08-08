"""Offline unit tests for the one shared duration parser."""

from __future__ import annotations

import unittest

from duration_parser import (
    has_remaining_duration_context,
    has_route_duration_context,
    parse_duration_minutes,
)


class DurationParserTests(unittest.TestCase):
    def test_supported_chinese_and_arabic_duration_expressions(self):
        cases = {
            "30分钟": 30,
            "三十分钟": 30,
            "半小时": 30,
            "半个钟头": 30,
            "一个小时": 60,
            "一小时": 60,
            "一个半小时": 90,
            "一小时半": 90,
            "1.5小时": 90,
            "1.5个小时": 90,
            "0.5小时": 30,
            "0.5个小时": 30,
            "1.25小时": 75,
            "两小时": 120,
            "一刻钟": 15,
            "三刻钟": 45,
            "2小时": 120,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                result = parse_duration_minutes(text)
                self.assertTrue(result.ok)
                self.assertEqual(result.minutes, expected)

    def test_two_hours_with_classifier_is_normalized(self):
        self.assertEqual(parse_duration_minutes("\u4e24\u4e2a\u5c0f\u65f6").minutes, 120)

    def test_common_english_minute_units_are_normalized(self):
        for text in ("30min", "30 mins", "30minute", "30 minutes", "30MIN"):
            with self.subTest(text=text):
                result = parse_duration_minutes(text)
                self.assertTrue(result.ok)
                self.assertEqual(result.minutes, 30)

    def test_english_minute_units_keep_route_context_boundary(self):
        self.assertTrue(has_route_duration_context("30min路线，木雕，详细"))
        self.assertFalse(has_route_duration_context("30min 后闭馆"))
        self.assertFalse(has_remaining_duration_context("30min 后闭馆"))

    def test_explicit_english_hour_is_normalized_without_guessing(self):
        for text, expected in (("one hour", 60), ("2 hours", 120)):
            with self.subTest(text=text):
                result = parse_duration_minutes(text)
                self.assertTrue(result.ok)
                self.assertEqual(result.minutes, expected)
        self.assertEqual(parse_duration_minutes("an hour").reason_code, "no_duration")
        self.assertTrue(has_route_duration_context("one hour tour"))

    def test_english_minute_unit_does_not_match_longer_word(self):
        result = parse_duration_minutes("30minimum")
        self.assertEqual(result.reason_code, "no_duration")

    def test_conflicting_duration_is_not_silently_selected(self):
        result = parse_duration_minutes("我有三十分钟或一个小时")
        self.assertEqual(result.reason_code, "ambiguous_duration")
        self.assertIsNone(result.minutes)

    def test_conflicting_english_durations_are_not_silently_selected(self):
        result = parse_duration_minutes("30min还是60 minutes")
        self.assertEqual(result.reason_code, "ambiguous_duration")
        self.assertIsNone(result.minutes)

    def test_fractional_minutes_are_not_treated_as_fractional_hours(self):
        result = parse_duration_minutes("1.5分钟")
        self.assertEqual(result.reason_code, "no_duration")
        self.assertIsNone(result.minutes)

    def test_decimal_hours_can_parse_beyond_profile_range_without_truncation(self):
        result = parse_duration_minutes("2.5小时")
        self.assertTrue(result.ok)
        self.assertEqual(result.minutes, 150)

    def test_non_duration_history_question_is_not_route_context(self):
        text = "陈家祠建了多少年？"
        self.assertEqual(parse_duration_minutes(text).reason_code, "no_duration")
        self.assertFalse(has_route_duration_context(text))
        self.assertFalse(has_remaining_duration_context(text))

    def test_route_and_remaining_contexts_are_distinguished(self):
        self.assertTrue(has_route_duration_context("我有一个小时，喜欢灰塑"))
        self.assertTrue(has_route_duration_context("给我规划一条半小时路线"))
        self.assertTrue(has_remaining_duration_context("我现在只剩三十分钟"))
        self.assertTrue(has_remaining_duration_context("把时间改成一个半小时"))
        self.assertFalse(has_remaining_duration_context("我有一个小时，喜欢灰塑"))


if __name__ == "__main__":
    unittest.main()
