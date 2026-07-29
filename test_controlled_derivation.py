"""Tests for evidence-bounded deterministic derivations."""

from __future__ import annotations

import unittest

from controlled_derivation import (
    ControlledDerivationError,
    DerivedOperand,
    deterministic_difference,
    deterministic_order,
)


class ControlledDerivationTests(unittest.TestCase):
    def test_time_difference_uses_both_reviewed_operands(self):
        result = deterministic_difference(
            operation="time_difference",
            start=DerivedOperand("筹建", 1888, (0,)),
            end=DerivedOperand("落成", 1893, (1,)),
            unit="年",
        )
        self.assertEqual(result["difference"], 5)
        self.assertTrue(result["deterministic"])

    def test_quantity_difference_is_deterministic(self):
        result = deterministic_difference(
            operation="quantity_difference",
            start=DerivedOperand("第一项数量", 7, (2,)),
            end=DerivedOperand("第二项数量", 12, (3,)),
            unit="件",
        )
        self.assertEqual(result["difference"], 5)
        self.assertEqual(result["unit"], "件")

    def test_chronological_order_is_stable(self):
        result = deterministic_order(
            [
                DerivedOperand("落成", 1893, (1,)),
                DerivedOperand("筹建", 1888, (0,)),
                DerivedOperand("另一口径", 1894, (2,)),
            ]
        )
        self.assertEqual(
            [item["label"] for item in result["items"]],
            ["筹建", "落成", "另一口径"],
        )

    def test_missing_evidence_fails_closed(self):
        with self.assertRaises(ControlledDerivationError):
            deterministic_difference(
                operation="time_difference",
                start=DerivedOperand("筹建", 1888, ()),
                end=DerivedOperand("落成", 1893, (1,)),
                unit="年",
            )

    def test_reversed_operands_fail_closed(self):
        with self.assertRaises(ControlledDerivationError):
            deterministic_difference(
                operation="quantity_difference",
                start=DerivedOperand("较大数量", 12, (0,)),
                end=DerivedOperand("较小数量", 7, (1,)),
                unit="件",
            )


if __name__ == "__main__":
    unittest.main()
