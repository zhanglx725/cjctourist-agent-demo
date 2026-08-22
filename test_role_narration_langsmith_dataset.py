from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from narration_style_policy import approved_style_ids
from tools.build_role_narration_langsmith_dataset import (
    DATASET_NAME, build_examples, load_project_env,
)


class RoleNarrationLangSmithDatasetTests(unittest.TestCase):
    def test_dotenv_loader_sets_missing_values_without_overwriting_shell(self):
        original = os.environ.get("ROLE_NARRATION_TEST_ENV")
        try:
            os.environ.pop("ROLE_NARRATION_TEST_ENV", None)
            with TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text("ROLE_NARRATION_TEST_ENV=from_dotenv\n", encoding="utf-8")
                load_project_env(path)
            self.assertEqual(os.environ["ROLE_NARRATION_TEST_ENV"], "from_dotenv")
            os.environ["ROLE_NARRATION_TEST_ENV"] = "from_shell"
            with TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text("ROLE_NARRATION_TEST_ENV=from_dotenv\n", encoding="utf-8")
                load_project_env(path)
            self.assertEqual(os.environ["ROLE_NARRATION_TEST_ENV"], "from_shell")
        finally:
            if original is None:
                os.environ.pop("ROLE_NARRATION_TEST_ENV", None)
            else:
                os.environ["ROLE_NARRATION_TEST_ENV"] = original

    def test_dataset_has_one_reviewed_case_per_style_and_point_type(self):
        examples = build_examples()
        self.assertEqual(DATASET_NAME, "chen-clan-academy-role-narration-stop-guidance-v1")
        self.assertEqual(len(examples), 54)
        self.assertEqual(
            {(item["inputs"]["style_id"], item["inputs"]["point_type"]) for item in examples},
            {(style_id, point_type) for style_id in approved_style_ids() for point_type in ("building", "craft", "ornament")},
        )

    def test_every_case_has_only_stop_guidance_and_a_complete_assertion_contract(self):
        for item in build_examples():
            with self.subTest(case_id=item["inputs"]["case_id"]):
                inputs, outputs = item["inputs"], item["outputs"]
                self.assertEqual(inputs["scene_kind"], "stop_guidance")
                self.assertEqual(outputs["expected_scene_kind"], "stop_guidance")
                self.assertTrue(inputs["approved_fact"])
                self.assertTrue(inputs["safety_boundaries"])
                self.assertTrue(inputs["required_style_markers"])
                self.assertEqual(outputs["expected_state_writes"], [])
                self.assertEqual(
                    outputs["expected_coverage_commit_count"],
                    0 if inputs["point_type"] == "building" else 1,
                )
                json.dumps(item, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
