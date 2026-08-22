from __future__ import annotations

import unittest

from photo_hint_card import build_photo_hint_card


class PhotoHintCardTests(unittest.TestCase):
    def test_structures_reviewed_photo_prose(self):
        card = build_photo_hint_card(
            "拍摄小提示：前庭门厅\n"
            "在允许停留的开阔位置自然站立，让门厅或中轴空间成为背景；"
            "可轻微侧身望向建筑。\n"
            "拍摄时请以现场光线、客流和开放情况为准。\n"
            "不得触摸或攀坐文物，现场规则请以馆方指引为准。"
        )
        self.assertEqual(card.title, "前庭门厅")
        self.assertIn("开阔位置", card.recommended_position)
        self.assertIn("背景", card.composition)
        self.assertIn("侧身", card.pose)
        self.assertIn("门厅", card.architecture)
        self.assertIn("光线", card.conditions)
        self.assertIn("不得触摸", card.safety)

    def test_missing_fields_fail_closed(self):
        card = build_photo_hint_card("拍摄小提示：月台\n请以馆方指引为准。")
        self.assertIn("未提供", card.recommended_position)
        self.assertIn("馆方", card.safety)


if __name__ == "__main__":
    unittest.main()
