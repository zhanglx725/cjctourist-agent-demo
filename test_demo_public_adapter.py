import unittest
from pathlib import Path

from langchain_core.messages import AIMessage

from agent_graph import (
    PublicMessage,
    PublicTourSummary,
    PublicTurnResult,
    _public_tour_summary,
    _public_turn_from_result,
)
from demo.demo_adapter import DemoAdapter


def _turn(*messages, current_stop="前院"):
    return PublicTurnResult(
        tuple(messages),
        PublicTourSummary(current_stop=current_stop, next_stop="聚贤堂", total_count=2, remaining_count=2),
    )


class DemoPublicAdapterTests(unittest.TestCase):
    def test_stop_guidance_projects_validated_service_tail_separately(self):
        service_text = "讲解结束后，您可确认是否完成本点。 完成本点后，下一站：月台。"
        result = _public_turn_from_result(
            {
                "messages": [AIMessage(
                    id="stop-1",
                    content=f"先看眼前的构件。\n\n{service_text}",
                    additional_kwargs={
                        "public_scene_kind": "stop_guidance",
                        "role_narration": True,
                        "stop_service_text": service_text,
                    },
                )],
            },
            after_last_human=False,
        )
        self.assertEqual(len(result.public_messages), 1)
        message = result.public_messages[0]
        self.assertEqual(message.text, "先看眼前的构件。")
        self.assertEqual(message.service_text, service_text)

    def test_deduplicates_by_message_id_and_uses_public_summary(self):
        route = PublicMessage("route-1", "route_planning", "路线正文", True)
        opening = PublicMessage("opening-1", "route_opening", "开场正文", True)
        calls = []

        def agent_call(text, thread_id):
            calls.append((text, thread_id))
            return _turn(route, opening)

        adapter = DemoAdapter(agent_call, session_starter=lambda _thread: _turn())
        first = adapter.send("规划")
        second = adapter.send("继续")
        self.assertEqual([item.message_id for item in first.messages], ["route-1", "opening-1"])
        self.assertTrue(second.is_error)
        self.assertEqual(adapter.itinerary.current_stop, "前院")
        self.assertEqual(len(calls), 2)

    def test_public_summary_exposes_ordered_stop_progress_without_ids(self):
        summary = _public_tour_summary({
            "tour_state": {
                "visited_stop_ids": ["p1_01_qianyuan"],
                "current_stop_id": "p1_02_zhongting",
                "remaining_stop_ids": ["p1_02_zhongting", "p1_03_juxiantang"],
            },
        })
        self.assertEqual(summary.completed_count, 1)
        self.assertEqual([stop.status for stop in summary.stops], ["completed", "current", "upcoming"])
        self.assertTrue(all("_" not in stop.name for stop in summary.stops))

    def test_reset_creates_an_isolated_thread_and_allows_fresh_display(self):
        message = PublicMessage("same-id", "stop_guidance", "讲解正文", False)
        adapter = DemoAdapter(
            lambda _text, _thread: _turn(message),
            session_starter=lambda _thread: _turn(message),
        )
        first_thread = adapter.thread_id
        self.assertFalse(adapter.send("我到了").is_error)
        adapter.reset()
        self.assertNotEqual(first_thread, adapter.thread_id)
        self.assertFalse(adapter.send("我到了").is_error)

    def test_start_uses_graph_owned_welcome_once_per_fresh_thread(self):
        welcome = PublicMessage("welcome-1", "welcome", "中文欢迎\n\nEnglish welcome", False)
        starts = []

        def starter(thread_id):
            starts.append(thread_id)
            return _turn(welcome)

        adapter = DemoAdapter(lambda _text, _thread: _turn(), session_starter=starter)
        first = adapter.start()
        second = adapter.start()
        self.assertFalse(first.is_error)
        self.assertTrue(second.is_error)
        self.assertEqual(len(starts), 2)
        adapter.reset()
        restarted = adapter.start()
        self.assertFalse(restarted.is_error)
        self.assertEqual(len(starts), 3)

    def test_demo_contains_no_checkpoint_reader_and_uses_arrival_literal(self):
        root = Path(__file__).resolve().parent
        adapter_source = (root / "demo" / "demo_adapter.py").read_text(encoding="utf-8")
        app_source = (root / "demo" / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("get_state", adapter_source)
        self.assertNotIn("tour_state", adapter_source)
        self.assertIn(
            'QUICK_ACTIONS = ["拍照提示", "我到了", "再讲详细一点", "完成本点"]',
            app_source,
        )

    def test_deploy_doc_has_active_settings_and_current_arrival_wording(self):
        document = (Path(__file__).resolve().parent / "demo" / "README_DEPLOY.md").read_text(encoding="utf-8")
        for value in (
            "CJC_READ_ONLY_ROLLOUT_MODE = \"read_only_active\"",
            "CJC_READ_ONLY_ROLLOUT_CAPABILITIES = \"role_narration,role_qa\"",
            "PRODUCT_ROLE_ACTIVE_ENABLED = \"true\"",
            "PRODUCT_ROLE_ACTIVE_SCENES = \"route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail,navigation,tour_closing,replan_presentation\"",
            "PRODUCT_ROLE_ROLLOUT_PERCENTAGE = \"100\"",
            "PRODUCT_ROLE_NATURAL_FULL_NARRATION_ENABLED = \"true\"",
            "“我到了”",
        ):
            self.assertIn(value, document)
        self.assertNotIn("我到前院中部了", document)


if __name__ == "__main__":
    unittest.main()
