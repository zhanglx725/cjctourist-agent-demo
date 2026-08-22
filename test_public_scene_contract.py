import unittest

from public_scene_contract import (
    PUBLIC_SCENE_CONTRACTS,
    PublicSceneKind,
    get_public_scene_contract,
    public_scene_kinds,
    render_arrival_confirmation,
    validate_navigation,
    validate_safety_refusal,
)


class PublicSceneContractTests(unittest.TestCase):
    def test_registry_contains_the_complete_p1_scene_set(self):
        self.assertEqual(
            public_scene_kinds(),
            (
                PublicSceneKind.ARRIVAL_CONFIRMATION,
                PublicSceneKind.ROUTE_OPENING,
                PublicSceneKind.STOP_GUIDANCE,
                PublicSceneKind.NAVIGATION,
                PublicSceneKind.TOUR_QA,
                PublicSceneKind.SAFETY_REFUSAL,
                PublicSceneKind.TOUR_CLOSING,
            ),
        )

    def test_each_contract_declares_all_required_boundary_fields(self):
        for kind, contract in PUBLIC_SCENE_CONTRACTS.items():
            with self.subTest(kind=kind):
                self.assertEqual(contract.kind, kind)
                self.assertTrue(contract.allowed_inputs)
                self.assertTrue(contract.required_semantics)
                self.assertTrue(contract.prohibited_semantics)
                self.assertTrue(contract.validator_name)
                self.assertTrue(contract.fallback_name)

    def test_arrival_contract_is_deterministic_and_excludes_point_opening(self):
        contract = get_public_scene_contract("arrival_confirmation")
        self.assertFalse(contract.llm_allowed)
        self.assertIn("arrived_display_name", contract.required_semantics)
        self.assertIn("begin_stop_guidance_now", contract.required_semantics)
        self.assertIn("point_opening_phrase", contract.prohibited_semantics)

    def test_qa_and_safety_contracts_do_not_allow_role_or_llm_generation(self):
        for kind in (PublicSceneKind.TOUR_QA, PublicSceneKind.SAFETY_REFUSAL):
            with self.subTest(kind=kind):
                contract = get_public_scene_contract(kind)
                self.assertFalse(contract.role_style_allowed)
                self.assertFalse(contract.llm_allowed)

    def test_safety_contract_bans_pre_safety_resolution_and_queries(self):
        contract = get_public_scene_contract(PublicSceneKind.SAFETY_REFUSAL)
        self.assertTrue({"location_resolution", "photo_candidate_query", "rag_query"}.issubset(contract.prohibited_semantics))

    def test_unknown_scene_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown public scene kind"):
            get_public_scene_contract("assistant")

    def test_arrival_renderer_is_one_deterministic_sentence(self):
        self.assertEqual(
            render_arrival_confirmation(" 前院中部 "),
            "你已到达前院中部，现在开始本点讲解。",
        )
        with self.assertRaisesRegex(ValueError, "requires a display name"):
            render_arrival_confirmation(" ")

    def test_navigation_validator_preserves_the_entire_deterministic_payload(self):
        expected = "下一站：月台\n从当前位置经 前院中部 => 月台 前往，预计步行约 30 秒。"
        self.assertTrue(validate_navigation(expected, deterministic_message=expected).accepted)
        rejected = validate_navigation(
            "我们先看看月台的故事。\n" + expected,
            deterministic_message=expected,
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason_codes, ("navigation_payload_changed",))

    def test_safety_validator_only_accepts_the_pre_decided_safety_reply(self):
        expected = "不建议踩栏杆拍照。请留在允许停留的平地取景。"
        self.assertTrue(validate_safety_refusal(
            expected,
            deterministic_message=expected,
            mode="photo_safety_refusal",
        ).accepted)
        rejected = validate_safety_refusal(
            "导游小贴士：" + expected,
            deterministic_message=expected,
            mode="photo_safety_refusal",
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.reason_codes, ("safety_payload_changed",))


if __name__ == "__main__":
    unittest.main()
