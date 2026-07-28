"""E5-0 contract skeleton: freeze required boundaries before implementation."""

from __future__ import annotations

from pathlib import Path
import unittest


CONTRACT = Path(__file__).with_name("E5_NARRATION_CONTRACT.md")


class E5NarrationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CONTRACT.read_text(encoding="utf-8")

    def test_contract_freezes_the_evidence_to_message_data_flow(self) -> None:
        for required in (
            "VisitorProfile",
            "GuidancePolicy",
            "StopProgram",
            "NarrationCoverage",
            "NarrationStylePolicy",
            "visitor_message",
        ):
            self.assertIn(required, self.text)

    def test_contract_keeps_coverage_outside_tour_state_and_profile(self) -> None:
        self.assertIn("不是 TourState、VisitorProfile", self.text)
        self.assertIn("只有 `confirm_stop_complete` 写入 visited", self.text)
        self.assertIn("不同 `thread_id` 天然隔离", self.text)

    def test_contract_freezes_all_eight_e5_acceptance_cases(self) -> None:
        for index in range(1, 9):
            self.assertIn(f"e5_nar_{index:03d}", self.text)

    def test_contract_defines_e5a_b_c_interfaces_without_production_writes(self) -> None:
        for required in (
            "plan_evidence_grounded_narration",
            "compile_narration_style",
            "evaluate_narration_case",
            "不得修改 TourState",
        ):
            self.assertIn(required, self.text)


if __name__ == "__main__":
    unittest.main()
