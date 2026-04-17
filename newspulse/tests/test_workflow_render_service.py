import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.context import AppContext
from newspulse.workflow import (
    HotlistItem,
    HTMLRenderAdapter,
    InsightResult,
    InsightSection,
    LocalizedReport,
    NotificationRenderAdapter,
    RenderService,
    RenderableReport,
    SelectionGroup,
    SelectionResult,
    StandaloneSection,
)
from newspulse.workflow.shared.options import RenderOptions


def _build_localized_report() -> LocalizedReport:
    item1 = HotlistItem(
        news_item_id="1",
        source_id="hackernews",
        source_name="Hacker News",
        title="OpenAI launches a new coding agent",
        url="https://example.com/1",
        current_rank=1,
        ranks=[1],
        first_time="2026-04-17 09:00:00",
        last_time="2026-04-17 10:00:00",
        count=1,
        is_new=True,
    )
    item2 = HotlistItem(
        news_item_id="2",
        source_id="producthunt",
        source_name="Product Hunt",
        title="Startup launches AI productivity app",
        url="https://example.com/2",
        current_rank=2,
        ranks=[2],
        first_time="2026-04-17 09:30:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )
    report = RenderableReport(
        meta={
            "mode": "current",
            "report_type": "实时报告",
            "timezone": "Asia/Hong_Kong",
        },
        selection=SelectionResult(
            strategy="keyword",
            groups=[SelectionGroup(key="ai", label="AI", items=[item1, item2], position=0)],
            selected_items=[item1, item2],
            total_candidates=2,
            total_selected=2,
        ),
        insight=InsightResult(
            enabled=True,
            strategy="ai",
            sections=[
                InsightSection(
                    key="core_trends",
                    title="核心趋势",
                    content="AI tools keep dominating the developer conversation.",
                )
            ],
            diagnostics={"analyzed_items": 2, "max_items": 10, "report_mode": "current"},
        ),
        new_items=[item1],
        standalone_sections=[StandaloneSection(key="producthunt", label="Product Hunt", items=[item2])],
        display_regions=["new_items", "hotlist", "standalone", "ai_analysis"],
    )
    return LocalizedReport(
        base_report=report,
        localized_titles={
            "1": "ZH:OpenAI launches a new coding agent",
            "2": "ZH:Startup launches AI productivity app",
        },
        localized_sections={
            "core_trends": "ZH:AI tools keep dominating the developer conversation.",
        },
        language="Chinese",
    )


class WorkflowRenderServiceTest(unittest.TestCase):
    def test_render_service_generates_html_and_delivery_payloads_from_localized_report(self):
        report = _build_localized_report()
        fixed_now = lambda: datetime(2026, 4, 17, 10, 30, 0)

        with TemporaryDirectory() as temp_dir:
            service = RenderService(
                html_adapter=HTMLRenderAdapter(
                    output_dir=temp_dir,
                    get_time_func=fixed_now,
                    date_folder_func=lambda: "2026-04-17",
                    time_filename_func=lambda: "103000",
                    display_mode="keyword",
                ),
                notification_adapter=NotificationRenderAdapter(
                    notification_channels=["generic_webhook"],
                    get_time_func=fixed_now,
                    display_mode="keyword",
                    batch_size=8000,
                ),
                display_mode="keyword",
                rank_threshold=5,
            )

            artifacts = service.run(
                report,
                RenderOptions(
                    display_regions=["new_items", "hotlist", "standalone", "ai_analysis"],
                    emit_html=True,
                    emit_notification=True,
                ),
            )

            html_path = Path(artifacts.html.file_path)
            self.assertTrue(html_path.exists())
            self.assertIn("ZH:OpenAI launches a new coding agent", artifacts.html.content)
            self.assertIn("ZH:AI tools keep dominating the developer conversation.", artifacts.html.content)
            self.assertEqual(artifacts.metadata["payload_count"], len(artifacts.payloads))
            self.assertTrue(artifacts.payloads)

            combined_payload = "\n".join(payload.content for payload in artifacts.payloads)
            self.assertIn("ZH:OpenAI launches a new coding agent", combined_payload)
            self.assertIn("ZH:AI tools keep dominating the developer conversation.", combined_payload)
            self.assertEqual(artifacts.payloads[0].channel, "generic_webhook")
            self.assertEqual(artifacts.metadata["display_regions"], ["new_items", "hotlist", "standalone", "ai_analysis"])

    def test_render_service_respects_display_regions_and_emit_switches(self):
        report = _build_localized_report()

        with TemporaryDirectory() as temp_dir:
            service = RenderService(
                html_adapter=HTMLRenderAdapter(
                    output_dir=temp_dir,
                    date_folder_func=lambda: "2026-04-17",
                    time_filename_func=lambda: "103000",
                ),
                notification_adapter=NotificationRenderAdapter(
                    notification_channels=["generic_webhook"],
                    batch_size=8000,
                ),
            )

            html_only = service.run(
                report,
                RenderOptions(
                    display_regions=["ai_analysis"],
                    emit_html=True,
                    emit_notification=False,
                ),
            )

            self.assertIn("ZH:AI tools keep dominating the developer conversation.", html_only.html.content)
            self.assertNotIn("ZH:OpenAI launches a new coding agent", html_only.html.content)
            self.assertEqual(html_only.payloads, [])

            notify_only = service.run(
                report,
                RenderOptions(
                    display_regions=["hotlist"],
                    emit_html=False,
                    emit_notification=True,
                ),
            )

            self.assertEqual(notify_only.html.file_path, "")
            self.assertTrue(notify_only.payloads)
            combined_payload = "\n".join(payload.content for payload in notify_only.payloads)
            self.assertIn("ZH:OpenAI launches a new coding agent", combined_payload)
            self.assertNotIn("ZH:AI tools keep dominating the developer conversation.", combined_payload)


class AppContextRenderStageTest(unittest.TestCase):
    def test_context_run_render_stage_uses_project_defaults_and_channel_config(self):
        report = _build_localized_report()

        with TemporaryDirectory() as temp_dir:
            ctx = AppContext(
                {
                    "TIMEZONE": "Asia/Hong_Kong",
                    "DISPLAY_MODE": "keyword",
                    "DISPLAY": {
                        "REGION_ORDER": ["hotlist", "ai_analysis", "standalone"],
                        "REGIONS": {
                            "NEW_ITEMS": False,
                        },
                    },
                    "STORAGE": {
                        "LOCAL": {
                            "DATA_DIR": temp_dir,
                        }
                    },
                }
            )

            artifacts = ctx.run_render_stage(report)

            html_path = Path(artifacts.html.file_path)
            self.assertTrue(html_path.exists())
            self.assertEqual(artifacts.payloads, [])
            self.assertEqual(artifacts.metadata["display_regions"], ["hotlist", "ai_analysis", "standalone"])
            self.assertFalse(artifacts.metadata["notification_enabled"])
            self.assertNotIn("本次新增热点", artifacts.html.content)


if __name__ == "__main__":
    unittest.main()
