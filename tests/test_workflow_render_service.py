import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory

from newspulse.runtime import build_runtime, run_render_stage
from newspulse.workflow import (
    HotlistItem,
    HTMLRenderAdapter,
    InsightSection,
    InsightSummary,
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
            report_type="Daily Report",
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
                    title="Core Trends",
                    content="AI tools keep dominating the developer conversation.",
                )
            ],
            summary_cards=[
                InsightSummary(
                    kind="report",
                    key="report",
                    title="报告摘要",
                    summary="2 条入选新闻形成 2 个主题：AI Agents、Startups",
                    item_ids=["1", "2"],
                    theme_keys=["theme:ai-agents", "theme:startups"],
                    evidence_topics=["AI Agents", "Startups"],
                    sources=["Hacker News", "Product Hunt"],
                ),
                InsightSummary(
                    kind="theme",
                    key="theme:ai-agents",
                    title="AI Agents",
                    summary="AI Agents 覆盖 1 条入选新闻，代表信号包括：OpenAI launches a new coding agent",
                    item_ids=["1"],
                    theme_keys=["theme:ai-agents"],
                    evidence_topics=["AI Agents", "Coding Workflow"],
                    evidence_notes=["clear developer workflow angle"],
                    sources=["Hacker News"],
                ),
                InsightSummary(
                    kind="item",
                    key="item:1",
                    title="OpenAI launches a new coding agent",
                    summary="Terminal-native coding workflow with patch and verify loops.",
                    item_ids=["1"],
                    theme_keys=["theme:ai-agents"],
                    evidence_topics=["AI Agents", "Coding Workflow"],
                    evidence_notes=["clear developer workflow angle"],
                    sources=["Hacker News"],
                    metadata={
                        "attributes": ["developer tools", "terminal"],
                        "semantic_score": 0.84,
                        "quality_score": 0.93,
                        "current_rank": 1,
                        "rank_trend": "up",
                        "source_kind": "article",
                    },
                ),
                InsightSummary(
                    kind="item",
                    key="item:2",
                    title="Startup launches AI productivity app",
                    summary="主题: Startups | 入选原因: startup launch with concrete workflow angle",
                    item_ids=["2"],
                    theme_keys=["theme:startups"],
                    evidence_topics=["Startups"],
                    evidence_notes=["startup launch with concrete workflow angle"],
                    sources=["Product Hunt"],
                    metadata={
                        "attributes": ["product launch"],
                        "semantic_score": 0.75,
                        "quality_score": 0.88,
                        "current_rank": 2,
                        "rank_trend": "stable",
                        "source_kind": "article",
                    },
                ),
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
                "summary_count": 4,
                "diagnostics": {
                    "summary_count": 4,
                    "item_summary_count": 2,
                    "theme_summary_count": 1,
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
        self.assertEqual(view_model.report_type, "Daily Report")
        self.assertEqual(view_model.hotlist_groups[0].items[0].title, "OpenAI launches a new coding agent")
        self.assertEqual(view_model.new_item_groups[0].items[0].title, "OpenAI launches a new coding agent")
        self.assertEqual(len(view_model.news_cards), 3)
        self.assertEqual(view_model.news_cards[0].summary.summary, "Terminal-native coding workflow with patch and verify loops.")
        self.assertEqual(len(view_model.summary_cards), 4)
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
            self.assertIn("摘要", artifacts.html.content)
            self.assertNotIn("结构化摘要", artifacts.html.content)
            self.assertNotIn("单条摘要", artifacts.html.content)
            self.assertNotIn("辅助来源属性", artifacts.html.content)
            self.assertNotIn("类型 article", artifacts.html.content)
            self.assertNotIn("入选原因", artifacts.html.content)
            self.assertIn("全局洞察", artifacts.html.content)
            self.assertNotIn("Weibo", artifacts.html.content)
            self.assertIn("Terminal-native coding workflow with patch and verify loops.", artifacts.html.content)
            self.assertIn("关键信号：startup launch with concrete workflow angle", artifacts.html.content)
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

    def test_render_service_surfaces_skipped_insight_reason_from_report_package(self):
        report = _build_report_package()
        report.content.insight_sections = []
        report.diagnostics["insight"] = {
            "enabled": False,
            "strategy": "noop",
            "summary_count": 0,
            "diagnostics": {
                "skipped": True,
                "reason": "schedule disabled",
                "report_mode": "current",
            },
        }

        view_model = build_render_view_model(
            report,
            display_mode="keyword",
            rank_threshold=5,
        )

        self.assertEqual(view_model.insight.status, "skipped")
        self.assertEqual(view_model.insight.message, "schedule disabled")

    def test_runtime_run_render_stage_uses_project_defaults_and_channel_config(self):
        report = _build_report_package()

        with TemporaryDirectory() as temp_dir:
            runtime = build_runtime(
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

            artifacts = run_render_stage(runtime.container, runtime.render_builder, report)

            html_path = Path(artifacts.html.file_path)
            self.assertTrue(html_path.exists())
            self.assertEqual(artifacts.payloads, [])
            self.assertEqual(artifacts.metadata["display_regions"], ["hotlist", "insight"])
            self.assertFalse(artifacts.metadata["notification_enabled"])
            self.assertIn('<header class="hero">', artifacts.html.content)


if __name__ == "__main__":
    unittest.main()
