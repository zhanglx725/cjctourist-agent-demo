"""Offline C1 tests for the pure VisitorProfile contract."""

from __future__ import annotations

import unittest

from visitor_profile import (
    DEFAULT_AVAILABLE_MINUTES,
    DEFAULT_AUDIENCE_MODE,
    DEFAULT_DETAIL_LEVEL,
    DEFAULT_EXPLANATION_STYLE,
    DEFAULT_INTERACTION_MODE,
    DEFAULT_KNOWLEDGE_LEVEL,
    VisitorProfile,
    VisitorProfileError,
    create_visitor_profile,
    profile_from_dict,
    update_visitor_profile,
)


class VisitorProfileTests(unittest.TestCase):
    def test_defaults_fill_only_neutral_non_sensitive_preferences(self):
        profile = VisitorProfile()
        self.assertEqual(profile.available_minutes, DEFAULT_AVAILABLE_MINUTES)
        self.assertEqual(profile.detail_level, DEFAULT_DETAIL_LEVEL)
        self.assertEqual(profile.interests, ())
        self.assertEqual(
            profile.to_dict(),
            {
                "available_minutes": 60,
                "interests": [],
                "detail_level": "standard",
                "audience_mode": DEFAULT_AUDIENCE_MODE,
                "knowledge_level": DEFAULT_KNOWLEDGE_LEVEL,
                "explanation_style": DEFAULT_EXPLANATION_STYLE,
                "interaction_mode": DEFAULT_INTERACTION_MODE,
            },
        )

    def test_normalization_is_stable_and_does_not_infer_future_preferences(self):
        profile = create_visitor_profile(
            available_minutes=45,
            interests=[" 灰塑 ", "木雕", "灰塑", "WOOD"],
            detail_level=" DEEP ",
        )
        self.assertEqual(profile.interests, ("灰塑", "木雕", "WOOD"))
        self.assertEqual(profile.detail_level, "deep")
        self.assertNotIn("visitor_type", profile.to_dict())
        self.assertNotIn("language", profile.to_dict())

    def test_validation_rejects_invalid_active_and_unknown_fields(self):
        for values in (
            {"available_minutes": 19},
            {"available_minutes": True},
            {"detail_level": "long"},
            {"interests": ["灰塑", 3]},
            {"unknown": "value"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(VisitorProfileError):
                    create_visitor_profile(**values)

    def test_optional_interfaces_are_only_explicit_and_strictly_validated(self):
        profile = create_visitor_profile(language=" EN ", photo_preference=True)
        self.assertEqual(profile.to_dict()["language"], "en")
        self.assertTrue(profile.to_dict()["photo_preference"])
        self.assertNotIn("visitor_type", profile.to_dict())
        with self.assertRaises(VisitorProfileError):
            create_visitor_profile(accessibility_need="yes")

    def test_route_constraint_is_explicit_optional_and_round_trips(self):
        profile = create_visitor_profile(route_constraint=" MINIMIZE_WALKING ")
        self.assertEqual(profile.route_constraint, "minimize_walking")
        self.assertEqual(
            profile_from_dict(profile.to_dict()).route_constraint,
            "minimize_walking",
        )
        with self.assertRaises(VisitorProfileError):
            create_visitor_profile(route_constraint="shortest_unverified")

    def test_update_is_immutable_and_can_clear_optional_values(self):
        original = create_visitor_profile(available_minutes=30, interests=["灰塑"], language="zh")
        updated = update_visitor_profile(original, available_minutes=45, interests=["木雕", "灰塑"], language=None)
        self.assertEqual(original.available_minutes, 30)
        self.assertEqual(original.interests, ("灰塑",))
        self.assertEqual(original.language, "zh")
        self.assertEqual(updated.available_minutes, 45)
        self.assertEqual(updated.interests, ("木雕", "灰塑"))
        self.assertNotIn("language", updated.to_dict())

    def test_serialization_and_deserialization_are_stable(self):
        profile = create_visitor_profile(available_minutes=75, interests=["灰塑", "木雕"], detail_level="standard")
        self.assertEqual(profile.to_json(), profile.to_json())
        restored = profile_from_dict(profile.to_dict())
        self.assertEqual(restored, profile)

    def test_c5_valid_choices_and_incremental_update_are_immutable(self):
        original = create_visitor_profile(
            audience_mode="family",
            knowledge_level="enthusiast",
            explanation_style="story",
            interaction_mode="interactive_tasks",
        )
        updated = update_visitor_profile(original, audience_mode="study", explanation_style="technical")
        self.assertEqual(original.audience_mode, "family")
        self.assertEqual(original.explanation_style, "story")
        self.assertEqual(updated.audience_mode, "study")
        self.assertEqual(updated.knowledge_level, "enthusiast")
        self.assertEqual(updated.explanation_style, "technical")
        self.assertEqual(updated.interaction_mode, "interactive_tasks")

    def test_c5_rejects_invalid_or_sensitive_ambiguous_fields(self):
        for values in (
            {"audience_mode": "teen"},
            {"knowledge_level": "doctor"},
            {"explanation_style": "funny"},
            {"interaction_mode": "always_chat"},
            {"visitor_type": "亲子家庭"},
            {"age": 10},
        ):
            with self.subTest(values=values):
                with self.assertRaises(VisitorProfileError):
                    create_visitor_profile(**values)

    def test_old_profile_and_legacy_visitor_type_are_compatible_without_mapping(self):
        restored = profile_from_dict(
            {
                "available_minutes": 30,
                "interests": ["灰塑"],
                "detail_level": "standard",
                "visitor_type": "亲子家庭",
            }
        )
        self.assertEqual(restored.available_minutes, 30)
        self.assertEqual(restored.audience_mode, "standard")
        self.assertNotIn("visitor_type", restored.to_dict())


if __name__ == "__main__":
    unittest.main()
