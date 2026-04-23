import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.context import AppContext
from newspulse.workflow import (
    HotlistItem,
    HTMLRenderAdapter,
    InsightSection,
    NotificationRenderAdapter,
    RenderService,
    ReportContent,
    ReportIntegrity,
    ReportPackage,
    ReportPackageMeta,
    SelectionGroup,
    StandaloneSection,
    build_render_view_model,
)
from newspulse.workflow.render import split_content_into_batches
from newspulse.workflow.shared.options import RenderOptions


def _build_report_package() -> ReportPackage:
    item1 = HotlistItem(
        news_item_id="1",
        source_id="hackernews",
        source_name="Hacker News",
        title="OpenAI launches a new coding agent",
        url="https://example.com/1",
        mobile_url="https://m.example.com/1",
        summary="Terminal-native coding workflow with patch and verify loops.",
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
        summary="A startup product launch aimed at AI-assisted productivity workflows.",
        current_rank=2,
        ranks=[2],
        first_time="2026-04-17 09:30:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )
    item3 = HotlistItem(
        news_item_id="3",
        source_id="github",
        source_name="GitHub",
        title="GitHub ships a new MCP toolkit",
        url="https://example.com/3",
        summary="Standalone platform signal that should still render as a first-class news card.",
        current_rank=4,
        ranks=[4],
        first_time="2026-04-17 08:30:00",
        last_time="2026-04-17 10:00:00",
        count=1,
    )
    return ReportPackage(
        meta=ReportPackageMeta(
            mode="current",
            report_type="中文示例简报",
            generated_at="2026-04-17 10:00:00",
            timezone="Asia/Hong_Kong",
            display_mode="keyword",
            selection_strategy="keyword",
            insight_strategy="ai",
        ),
        content=ReportContent(
            hotlist_groups=[SelectionGroup(key="ai", label="AI", items=[item1, item2], position=0)],
            selected_items=[item1, item2],
            new_items=[item1],
            standalone_sections=[
                StandaloneSection(
                    key="github",
                    label="GitHub",
                    items=[item3],
                    description="Pinned standalone signal",
                )
            ],
            insight_sections=[
                InsightSection(
                    key="core_trends",
                    title="综合判断",
                    content="AI tools keep dominating the developer conversation.",
                )
            ],
        ),
        integrity=ReportIntegrity(valid=True, counters={"selected_item_count": 2}),
        diagnostics={
            "snapshot_summary": {"total_items": 2},
            "selection": {
                "strategy": "keyword",
                "diagnostics": {
                    "selected_matches": [
                        {
                            "news_item_id": "1",
                            "quality_score": 0.93,
                            "decision_layer": "llm_quality_gate",
                            "reasons": ["high-signal launch", "clear developer workflow angle"],
                            "matched_topics": ["AI Agents", "Coding Workflow"],
                            "evidence": "Terminal workflow and patch loop make the signal concrete.",
                        },
                        {
                            "news_item_id": "2",
                            "quality_score": 0.88,
                            "decision_layer": "llm_quality_gate",
                            "reasons": ["startup launch with concrete workflow angle"],
                            "matched_topics": ["Startups"],
                            "evidence": "Product launch is relevant to downstream workflow tooling.",
                        },
                    ]
                },
            },
            "insight": {
                "enabled": True,
                "strategy": "ai",
                "item_analysis_count": 2,
                "diagnostics": {
                    "analyzed_items": 2,
                    "max_items": 10,
                    "report_mode": "current",
                    "input_contexts": [
                        {
                            "news_item_id": "1",
                            "source_context": {
                                "summary": "Hacker News item with direct developer adoption signal.",
                                "attributes": ["developer tools", "terminal"],
                            },
                            "selection_evidence": {
                                "matched_topics": ["AI Agents", "Coding Workflow"],
                                "semantic_score": 0.84,
                                "quality_score": 0.93,
                                "decision_layer": "llm_quality_gate",
                                "llm_reasons": ["clear developer workflow angle"],
                            },
                        },
                        {
                            "news_item_id": "2",
                            "source_context": {
                                "summary": "Product Hunt launch with startup distribution context.",
                                "attributes": ["product launch"],
                            },
                            "selection_evidence": {
                                "matched_topics": ["Startups"],
                                "semantic_score": 0.75,
                                "quality_score": 0.88,
                                "decision_layer": "llm_quality_gate",
                                "llm_reasons": ["startup launch with concrete workflow angle"],
                            },
                        },
                    ],
                    "item_analysis_payloads": [
                        {
                            "news_item_id": "1",
                            "title": "OpenAI launches a new coding agent",
                            "what_happened": "OpenAI shipped a terminal-native coding agent workflow.",
                            "key_facts": ["Patch loop is built-in", "Verification is part of the default flow"],
                            "why_it_matters": "It reduces the gap between demo agents and repeatable engineering work.",
                            "watchpoints": ["Whether repository-level controls appear next"],
                            "uncertainties": ["How much autonomy teams will allow in production"],
                            "evidence": ["Workflow explicitly includes patch and verify steps"],
                            "confidence": 0.86,
                            "diagnostics": {"status": "ok"},
                        },
                        {
                            "news_item_id": "2",
                            "title": "Startup launches AI productivity app",
                            "what_happened": "A startup released a productivity workflow tool with AI copilots.",
                            "key_facts": ["Targets productivity use cases", "Competes in workflow tooling"],
                            "why_it_matters": "It shows the product layer is racing to package AI into repeatable work habits.",
                            "watchpoints": ["Retention versus novelty adoption"],
                            "uncertainties": [],
                            "evidence": ["Product Hunt launch timing indicates GTM push"],
                            "confidence": 0.79,
                            "diagnostics": {"status": "ok"},
                        },
                    ],
                },
            },
            "failed_sources": [{"source_id": "weibo", "source_name": "Weibo"}],
        },
    )


class WorkflowRenderServiceTest(unittest.TestCase):
    def test_build_render_view_model_consumes_report_package(self):
        report = _build_report_package()

        view_model = build_render_view_model(
            report,
            display_mode="keyword",
            rank_threshold=5,
        )

        self.assertEqual(view_model.total_titles, 2)
        self.assertEqual(view_model.mode, "current")
        self.assertEqual(view_model.report_type, "中文示例简报")
        self.assertEqual(view_model.hotlist_groups[0].items[0].title, "OpenAI launches a new coding agent")
        self.assertEqual(view_model.new_item_groups[0].items[0].title, "OpenAI launches a new coding agent")
        self.assertEqual(len(view_model.news_cards), 3)
        self.assertEqual(view_model.news_cards[0].analysis.what_happened, "OpenAI shipped a terminal-native coding agent workflow.")
        self.assertEqual(view_model.news_cards[0].selection_evidence.matched_topics, ["AI Agents", "Coding Workflow"])
        self.assertTrue(view_model.news_cards[2].is_standalone)
        self.assertEqual(view_model.insight.sections[0].content, "AI tools keep dominating the developer conversation.")
        self.assertEqual(view_model.failed_source_names, ["Weibo"])

    def test_notification_splitter_consumes_report_package_view_model(self):
        report = _build_report_package()
        view_model = build_render_view_model(
            report,
            display_mode="keyword",
            rank_threshold=5,
        )

        batches = split_content_into_batches(
            view_model,
            format_type="wework",
            max_bytes=8000,
            get_time_func=lambda: datetime(2026, 4, 17, 10, 30, 0),
        )

        combined = "\n".join(batches)
        self.assertTrue(batches)
        self.assertIn("OpenAI launches a new coding agent", combined)
        self.assertIn("AI tools keep dominating the developer conversation.", combined)

    def test_render_service_generates_html_and_delivery_payloads_from_report_package(self):
        report = _build_report_package()

        def fixed_now():
            return datetime(2026, 4, 17, 10, 30, 0)

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
                    display_regions=["new_items", "hotlist", "insight"],
                    emit_html=True,
                    emit_notification=True,
                ),
            )

            html_path = Path(artifacts.html.file_path)
            self.assertTrue(html_path.exists())
            self.assertIn("OpenAI launches a new coding agent", artifacts.html.content)
            self.assertIn("新闻卡片", artifacts.html.content)
            self.assertIn("LLM Analysis", artifacts.html.content)
            self.assertNotIn("Why this story made the cut", artifacts.html.content)
            self.assertNotIn("Weibo", artifacts.html.content)
            self.assertNotIn("不再按来源堆叠输出，而是把每条新闻作为独立阅读单元，只展示新闻信息与 LLM 分析。", artifacts.html.content)
            self.assertIn("OpenAI shipped a terminal-native coding agent workflow.", artifacts.html.content)
            self.assertIn("AI tools keep dominating the developer conversation.", artifacts.html.content)
            self.assertIn('data-story-search', artifacts.html.content)
            self.assertIn('data-source-filter="all"', artifacts.html.content)
            self.assertIn('class="story-badge source js-source-filter"', artifacts.html.content)
            self.assertIn('data-story-empty', artifacts.html.content)
            self.assertIn('data-toggle-target="aggregate-content"', artifacts.html.content)
            self.assertIn('@media (prefers-color-scheme: dark)', artifacts.html.content)
            self.assertIn("const storyCards = Array.from(document.querySelectorAll('[data-story-card]'))", artifacts.html.content)
            self.assertEqual(artifacts.metadata["payload_count"], len(artifacts.payloads))
            self.assertTrue(artifacts.payloads)
            self.assertTrue(artifacts.metadata["integrity_valid"])

            combined_payload = "\n".join(payload.content for payload in artifacts.payloads)
            self.assertIn("OpenAI launches a new coding agent", combined_payload)
            self.assertIn("AI tools keep dominating the developer conversation.", combined_payload)
            self.assertEqual(artifacts.payloads[0].channel, "generic_webhook")
            self.assertEqual(artifacts.metadata["display_regions"], ["new_items", "hotlist", "insight"])

    def test_render_service_respects_display_regions_and_emit_switches(self):
        report = _build_report_package()

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
                    display_regions=["insight"],
                    emit_html=True,
                    emit_notification=False,
                ),
            )

            self.assertIn("AI tools keep dominating the developer conversation.", html_only.html.content)
            self.assertNotIn("OpenAI launches a new coding agent", html_only.html.content)
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
            self.assertIn("OpenAI launches a new coding agent", combined_payload)
            self.assertNotIn("AI tools keep dominating the developer conversation.", combined_payload)

    def test_render_service_surfaces_skipped_insight_reason_from_report_package(self):
        report = _build_report_package()
        report.content.insight_sections = []
        report.diagnostics["insight"] = {
            "enabled": False,
            "strategy": "noop",
            "item_analysis_count": 0,
            "diagnostics": {
                "skipped": True,
                "reason": "schedule disabled",
                "report_mode": "current",
            },
        }

        def fixed_now():
            return datetime(2026, 4, 17, 10, 30, 0)

        view_model = build_render_view_model(
            report,
            display_mode="keyword",
            rank_threshold=5,
        )

        self.assertEqual(view_model.insight.status, "skipped")
        self.assertEqual(view_model.insight.message, "schedule disabled")

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
                    display_regions=["insight"],
                    emit_html=True,
                    emit_notification=True,
                ),
            )

            combined_payload = "\n".join(payload.content for payload in artifacts.payloads)
            self.assertIn("schedule disabled", artifacts.html.content)
            self.assertIn("schedule disabled", combined_payload)


class AppContextRenderStageTest(unittest.TestCase):
    def test_context_run_render_stage_uses_project_defaults_and_channel_config(self):
        report = _build_report_package()

        with TemporaryDirectory() as temp_dir:
            ctx = AppContext(
                {
                    "TIMEZONE": "Asia/Hong_Kong",
                    "DISPLAY_MODE": "keyword",
                    "DISPLAY": {
                        "REGION_ORDER": ["hotlist", "insight", "standalone"],
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
            self.assertEqual(artifacts.metadata["display_regions"], ["hotlist", "insight"])
            self.assertFalse(artifacts.metadata["notification_enabled"])
            self.assertIn("本批重点新闻分析", artifacts.html.content)
            self.assertNotIn("Weibo", artifacts.html.content)

    def test_context_run_render_stage_filters_disabled_new_item_region_even_if_order_keeps_it(self):
        report = _build_report_package()

        with TemporaryDirectory() as temp_dir:
            ctx = AppContext(
                {
                    "TIMEZONE": "Asia/Hong_Kong",
                    "DISPLAY_MODE": "keyword",
                    "DISPLAY": {
                        "REGION_ORDER": ["hotlist", "new_items", "insight", "standalone"],
                        "REGIONS": {
                            "HOTLIST": True,
                            "NEW_ITEMS": False,
                            "STANDALONE": True,
                            "INSIGHT": True,
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

            self.assertEqual(artifacts.metadata["display_regions"], ["hotlist", "insight", "standalone"])
            self.assertNotIn('story-badge accent">新增</span>', artifacts.html.content)


if __name__ == "__main__":
    unittest.main()
