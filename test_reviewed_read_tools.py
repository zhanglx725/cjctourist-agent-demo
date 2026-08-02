"""CA-03 read-tool adapters must preserve reviewed facts and input state."""

from __future__ import annotations

from copy import deepcopy
import unittest

from reviewed_read_tools import (
    answer_reviewed_service_rule,
    answer_reviewed_single_fact,
    answer_reviewed_term,
)


HISTORY_EVIDENCE = [{
    "category": "history_architecture", "source_ids": ["S02"],
    "content": "陈氏书院于 1888 年开始筹建，1893 年落成。",
}]
INVOICE_EVIDENCE = [{
    "category": "ticketing_snapshot", "source_ids": ["S05"],
    "content": "团队订单电子发票可在购买后30日内申请。发票一经开具不能修改，也不能办理退票。",
}]


class ReviewedReadToolTests(unittest.TestCase):
    def test_single_fact_is_state_free_evidence_bounded_and_public(self):
        evidence = deepcopy(HISTORY_EVIDENCE)
        result = answer_reviewed_single_fact("陈家祠什么时候开始筹建？", evidence)
        self.assertEqual(result.capability, "single_fact")
        self.assertEqual(result.status, "ok")
        self.assertIn("1888 年", result.message)
        self.assertEqual(result.audit["source_ids"], ["S02"])
        self.assertEqual(evidence, HISTORY_EVIDENCE)
        for token in ("S02", "source_ids", ".md", "tour_state"):
            self.assertNotIn(token, result.message)

    def test_single_fact_fails_closed_for_wrong_or_absent_evidence(self):
        result = answer_reviewed_single_fact("陈家祠什么时候开始筹建？", [])
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIn("资料不足", result.message)
        unrecognized = answer_reviewed_single_fact("详细讲讲陈家祠", HISTORY_EVIDENCE)
        self.assertEqual(unrecognized.status, "not_eligible")

    def test_civil_service_boundary_is_not_misrepresented_as_ticketing_fact(self):
        result = answer_reviewed_single_fact("身份证丢了怎么挂失？", [])
        self.assertEqual(result.status, "outside_venue_scope")
        self.assertIn("公安机关官方渠道", result.message)
        self.assertNotIn("综合服务处", result.message)

    def test_term_adapter_does_not_receive_tour_state_or_execute_backend_mutation(self):
        calls = []

        def answerer(query, tour_state, interaction_state):
            calls.append((query, tour_state, interaction_state))
            return {"message": "灰塑是一种建筑装饰工艺。", "mode": "term_card", "term": {"card_id": "term_001", "source_ids": ["S10"]}, "evidence": []}

        result = answer_reviewed_term("灰塑是什么？", term_answerer=answerer)
        self.assertEqual(calls, [("灰塑是什么？", None, None)])
        self.assertEqual(result.status, "term_card")
        self.assertEqual(result.audit["source_ids"], ["S10"])
        self.assertNotIn("S10", result.message)

    def test_service_rule_uses_only_scoped_evidence_and_deterministic_invoice_path(self):
        calls = []
        result = answer_reviewed_service_rule(
            "团队订单电子发票规则", INVOICE_EVIDENCE,
            invoke_model=lambda prompt: calls.append(prompt) or "不应调用模型",
        )
        self.assertEqual(result.capability, "visit_service")
        self.assertEqual(result.status, "ok")
        self.assertIn("30 日内", result.message)
        self.assertEqual(calls, [])
        self.assertEqual(result.audit["source_ids"], ["S05"])
        self.assertNotIn("S05", result.message)

    def test_service_rule_rejects_unscoped_or_missing_evidence(self):
        result = answer_reviewed_service_rule(
            "团队订单电子发票规则",
            [{"category": "history_architecture", "content": "无关资料", "source_ids": ["S02"]}],
            invoke_model=lambda _: "不应使用",
        )
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIn("资料不足", result.message)
        unrecognized = answer_reviewed_service_rule("陈家祠有什么特点？", [], invoke_model=lambda _: "不应使用")
        self.assertEqual(unrecognized.status, "not_eligible")


if __name__ == "__main__":
    unittest.main()
