from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from role_narration_style_evaluator import (
    evaluate_role_narration_style, style_quality_prompt,
)


class RoleNarrationStyleEvaluatorTests(unittest.TestCase):
    def test_prompt_is_expression_only_and_contains_scoring_contract(self):
        prompt = style_quality_prompt(style_id="ancient_scholar", public_text="诸位且看，审核事实。")
        self.assertIn("只评价表达", prompt)
        self.assertIn("不得建议补充人物、年代、典故", prompt)
        self.assertIn("role_fit", prompt)
        self.assertIn("诸位且看", prompt)

    def test_missing_key_returns_unavailable_without_network(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False):
            result = evaluate_role_narration_style(style_id="neutral", public_text="审核事实。")
        self.assertEqual(result["status"], "unavailable")

    def test_valid_model_score_is_normalized(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False), patch(
            "role_narration_style_evaluator.ChatDeepSeek"
        ) as model_cls:
            model_cls.return_value.invoke.return_value.content = (
                '{"role_fit":2,"naturalness":2,"distinctiveness":1,"readability":2,"rationale":"语气自然，角色特征清楚。"}'
            )
            result = evaluate_role_narration_style(style_id="ancient_scholar", public_text="诸位且看，审核事实。")
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["average_score"], 1.75)

    def test_invalid_model_schema_fails_closed_as_unavailable(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=False), patch(
            "role_narration_style_evaluator.ChatDeepSeek"
        ) as model_cls:
            model_cls.return_value.invoke.return_value.content = '{"role_fit":3}'
            result = evaluate_role_narration_style(style_id="neutral", public_text="审核事实。")
        self.assertEqual(result, {"status": "unavailable", "reason": "invalid_judge_schema"})


if __name__ == "__main__":
    unittest.main()
