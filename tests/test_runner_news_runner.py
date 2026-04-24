import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from newspulse.crawler import CrawlBatchResult, CrawlSourceSpec, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.runner import NewsRunner
from newspulse.workflow import (
    DeliveryPayload,
    HTMLArtifact,
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    RenderArtifacts,
    ReportContent,
    ReportIntegrity,
    ReportPackage,
    ReportPackageMeta,
    SelectionGroup,
    SelectionResult,
)


def _build_snapshot(*, mode="current", total_selected=1) -> tuple[HotlistSnapshot, SelectionResult]:
    items = []
    if total_selected > 0:
        item = HotlistItem(
            news_item_id="1",
            source_id="hackernews",
            source_name="Hacker News",
            title="OpenAI launches a new coding agent",
            current_rank=1,
            ranks=[1],
        )
        items = [item]

    snapshot = HotlistSnapshot(
        mode=mode,
        generated_at="2026-04-17 10:30:00",
        items=items,
        new_items=items if mode == "daily" else [],
        summary={"total_items": len(items)},
    )
    selection = SelectionResult(
        strategy="keyword",
        groups=[SelectionGroup(key="ai", label="AI", items=items, position=0)] if items else [],
        selected_items=items,
        selected_new_items=snapshot.new_items,
        total_candidates=len(items),
        total_selected=len(items),
    )
    return snapshot, selection


class FakeScheduler:
    def __init__(self, schedule, *, already_executed=False):
        self.schedule = schedule
        self._already_executed = already_executed
        self.already_calls = []
        self.recorded = []

    def resolve(self):
        return self.schedule

    def already_executed(self, period_key, action, date_str):
        self.already_calls.append((period_key, action, date_str))
        return self._already_executed

    def record_execution(self, period_key, action, date_str):
        self.recorded.append((period_key, action, date_str))


class FakeStorageManager:
    def __init__(self):
        self.backend_name = "fake"
        self.saved_batch = None
        self.txt_snapshot_data = None

    def save_normalized_crawl_batch(self, batch):
        self.saved_batch = batch
        return True

    def save_txt_snapshot(self, data):
        self.txt_snapshot_data = data
        return "output/txt/latest.txt"


class FakeFetcher:
    def __init__(self, batch_result: CrawlBatchResult):
        self.batch_result = batch_result
        self.calls = []

    def crawl(self, source_specs, request_interval):
        self.calls.append((source_specs, request_interval))
        return self.batch_result


class NewsRunnerWorkflowStageTest(unittest.TestCase):
    def _build_runner(self, scheduler, render_result) -> NewsRunner:
        runner = NewsRunner.__new__(NewsRunner)
        runner.runtime = SimpleNamespace(
            selection_builder=object(),
            insight_builder=object(),
            render_builder=object(),
            delivery_builder=object(),
            cleanup=lambda: None,
        )
        runner.settings = SimpleNamespace(
            crawler=SimpleNamespace(enabled=True, crawl_source_specs=[], proxy_enabled=False, default_proxy_url=""),
            storage=SimpleNamespace(enable_html=True, data_dir=Path("output"), retention_days=7),
            selection=SimpleNamespace(strategy="keyword", rank_threshold=5),
            delivery=SimpleNamespace(enabled=True, generic_webhook_url="https://example.com/webhook"),
            app=SimpleNamespace(show_version_update=True, debug_enabled=False),
            format_date=lambda: "2026-04-17",
            format_time=lambda: "2026-04-17 10:30:00",
            get_time=lambda: None,
        )
        runner.container = SimpleNamespace(
            scheduler=lambda: scheduler,
            storage=lambda: FakeStorageManager(),
        )
        runner.report_mode = "daily"
        runner.frequency_file = None
        runner.filter_method = None
        runner.interests_file = None
        runner.update_info = {"current_version": "1.0.0", "remote_version": "1.1.0"}
        runner.proxy_url = "http://127.0.0.1:1080"
        runner.is_github_actions = True
        runner.is_docker_container = False
        runner.data_fetcher = FakeFetcher(CrawlBatchResult())
        runner.storage_manager = FakeStorageManager()
        runner._render_result = render_result
        return runner

    def test_crawl_data_uses_native_batch_contract(self):
        batch_result = CrawlBatchResult(
            sources=[
                SourceFetchResult(
                    source_id="hackernews",
                    source_name="Hacker News",
                    resolved_source_id="hackernews",
                    items=[
                        SourceItem(title="Alpha", url="https://example.com/a"),
                        SourceItem(title="Alpha", url="https://example.com/a2"),
                        SourceItem(title="Beta", url="https://example.com/b"),
                    ],
                )
            ],
            failures=[
                SourceFetchFailure(
                    source_id="thepaper",
                    source_name="The Paper",
                    resolved_source_id="thepaper",
                    exception_type="TimeoutError",
                    message="timeout",
                )
            ],
        )

        runner = NewsRunner.__new__(NewsRunner)
        runner.settings = SimpleNamespace(
            crawler=SimpleNamespace(
                crawl_source_specs=[
                    CrawlSourceSpec(source_id="hackernews", source_name="Hacker News"),
                    CrawlSourceSpec(source_id="thepaper", source_name="The Paper"),
                ]
            ),
            storage=SimpleNamespace(data_dir=Path("output")),
            format_time=lambda: "2026-04-17 10:30:00",
            format_date=lambda: "2026-04-17",
        )
        runner.request_interval = 0
        runner.data_fetcher = FakeFetcher(batch_result)
        runner.storage_manager = FakeStorageManager()

        crawl_batch = runner._crawl_data()

        self.assertIs(crawl_batch, batch_result)
        source_specs, request_interval = runner.data_fetcher.calls[0]
        self.assertEqual(request_interval, 0)
        self.assertEqual(
            source_specs,
            [
                CrawlSourceSpec(source_id="hackernews", source_name="Hacker News"),
                CrawlSourceSpec(source_id="thepaper", source_name="The Paper"),
            ],
        )
        saved_batch = runner.storage_manager.saved_batch
        self.assertIsNotNone(saved_batch)
        self.assertEqual(saved_batch.id_to_name["hackernews"], "Hacker News")
        self.assertEqual(saved_batch.id_to_name["thepaper"], "The Paper")
        self.assertEqual(saved_batch.failed_ids, ["thepaper"])
        self.assertEqual(len(saved_batch.items["hackernews"]), 2)
        self.assertEqual(saved_batch.failures[0].exception_type, "TimeoutError")
        alpha = next(item for item in saved_batch.items["hackernews"] if item.title == "Alpha")
        self.assertEqual(alpha.ranks, [1, 2])
        self.assertEqual(runner.storage_manager.txt_snapshot_data, saved_batch)

    def test_init_storage_manager_only_depends_on_runtime_contract(self):
        runner = NewsRunner.__new__(NewsRunner)
        runner.container = SimpleNamespace(storage=lambda: FakeStorageManager())
        runner.settings = SimpleNamespace(storage=SimpleNamespace(retention_days=7))

        runner._init_storage_manager()

        self.assertEqual(runner.storage_manager.backend_name, "fake")

    def test_execute_mode_strategy_runs_native_stage_chain(self):
        snapshot, selection = _build_snapshot(mode="current", total_selected=1)
        schedule = SimpleNamespace(
            report_mode="current",
            frequency_file="freq.txt",
            filter_method="ai",
            interests_file="interests.txt",
            push=True,
            once_push=True,
            period_key="morning",
            period_name="早报",
        )
        scheduler = FakeScheduler(schedule)
        render_result = RenderArtifacts(
            html=HTMLArtifact(file_path="output/html/2026-04-17/103000.html", content="<html></html>"),
            payloads=[DeliveryPayload(channel="generic_webhook", title="测试推送", content="payload")],
        )
        runner = self._build_runner(scheduler, render_result)
        report_package = ReportPackage(
            meta=ReportPackageMeta(mode=snapshot.mode, report_type="测试报告"),
            content=ReportContent(
                hotlist_groups=selection.groups,
                selected_items=selection.selected_items,
                new_items=selection.selected_new_items,
                standalone_sections=snapshot.standalone_sections,
                insight_sections=[],
            ),
            integrity=ReportIntegrity(valid=True),
            diagnostics={"insight": {"enabled": True, "strategy": "ai", "diagnostics": {}}, "failed_sources": []},
        )
        insight = InsightResult(enabled=True, strategy="ai")

        with (
            patch("newspulse.runner.news_runner.run_selection_stage", return_value=(snapshot, selection)) as run_selection,
            patch("newspulse.runner.news_runner.run_insight_stage", return_value=insight) as run_insight,
            patch("newspulse.runner.news_runner.assemble_report_package", return_value=report_package) as assemble_report,
            patch("newspulse.runner.news_runner.run_render_stage", return_value=render_result) as run_render,
            patch(
                "newspulse.runner.news_runner.run_delivery_stage",
                return_value=SimpleNamespace(success=True, channel_results=[{"channel": "generic_webhook"}]),
            ) as run_delivery,
        ):
            html_file = runner._execute_mode_strategy(runner._get_mode_strategy(), schedule=schedule)

        self.assertEqual(html_file, "output/html/2026-04-17/103000.html")
        self.assertEqual(run_selection.call_args.kwargs["mode"], "current")
        self.assertEqual(run_selection.call_args.kwargs["strategy"], "ai")
        self.assertIs(run_insight.call_args.kwargs["snapshot"], snapshot)
        self.assertIs(run_insight.call_args.kwargs["selection"], selection)
        self.assertTrue(run_render.call_args.kwargs["emit_html"])
        self.assertTrue(run_render.call_args.kwargs["emit_notification"])
        self.assertEqual(run_render.call_args.kwargs["update_info"]["remote_version"], "1.1.0")
        self.assertEqual(run_delivery.call_args.kwargs["proxy_url"], "http://127.0.0.1:1080")
        self.assertEqual(scheduler.recorded, [("morning", "push", "2026-04-17")])
        assemble_report.assert_called_once()

    def test_execute_mode_strategy_skips_delivery_when_no_notifiable_content(self):
        snapshot, selection = _build_snapshot(mode="current", total_selected=0)
        schedule = SimpleNamespace(
            report_mode="current",
            frequency_file=None,
            filter_method=None,
            interests_file=None,
            push=True,
            once_push=False,
            period_key=None,
            period_name=None,
        )
        scheduler = FakeScheduler(schedule)
        render_result = RenderArtifacts(
            html=HTMLArtifact(file_path="output/html/2026-04-17/103000.html", content="<html></html>"),
            payloads=[],
        )
        runner = self._build_runner(scheduler, render_result)
        report_package = ReportPackage(
            meta=ReportPackageMeta(mode=snapshot.mode, report_type="测试报告"),
            content=ReportContent(
                hotlist_groups=selection.groups,
                selected_items=selection.selected_items,
                new_items=selection.selected_new_items,
                standalone_sections=snapshot.standalone_sections,
                insight_sections=[],
            ),
            integrity=ReportIntegrity(valid=True),
        )

        with (
            patch("newspulse.runner.news_runner.run_selection_stage", return_value=(snapshot, selection)),
            patch("newspulse.runner.news_runner.run_insight_stage", return_value=InsightResult(enabled=True, strategy="ai")),
            patch("newspulse.runner.news_runner.assemble_report_package", return_value=report_package),
            patch("newspulse.runner.news_runner.run_render_stage", return_value=render_result) as run_render,
            patch("newspulse.runner.news_runner.run_delivery_stage") as run_delivery,
        ):
            runner._execute_mode_strategy(runner._get_mode_strategy(), schedule=schedule)

        self.assertFalse(run_render.call_args.kwargs["emit_notification"])
        self.assertFalse(run_delivery.called)
        self.assertEqual(scheduler.already_calls, [])
        self.assertEqual(scheduler.recorded, [])

    def test_execute_mode_strategy_skips_delivery_when_report_package_invalid(self):
        snapshot, selection = _build_snapshot(mode="current", total_selected=1)
        schedule = SimpleNamespace(
            report_mode="current",
            frequency_file=None,
            filter_method=None,
            interests_file=None,
            push=True,
            once_push=False,
            period_key=None,
            period_name=None,
        )
        scheduler = FakeScheduler(schedule)
        render_result = RenderArtifacts(
            html=HTMLArtifact(file_path="output/html/2026-04-17/103000.html", content="<html></html>"),
            payloads=[DeliveryPayload(channel="generic_webhook", title="实时报告", content="payload")],
        )
        runner = self._build_runner(scheduler, render_result)
        report_package = ReportPackage(
            meta=ReportPackageMeta(mode=snapshot.mode, report_type="测试报告"),
            content=ReportContent(
                hotlist_groups=selection.groups,
                selected_items=selection.selected_items,
                new_items=selection.selected_new_items,
                standalone_sections=snapshot.standalone_sections,
                insight_sections=[],
            ),
            integrity=ReportIntegrity(valid=False, errors=["snapshot linkage missing"]),
        )

        with (
            patch("newspulse.runner.news_runner.run_selection_stage", return_value=(snapshot, selection)),
            patch("newspulse.runner.news_runner.run_insight_stage", return_value=InsightResult(enabled=True, strategy="ai")),
            patch("newspulse.runner.news_runner.assemble_report_package", return_value=report_package),
            patch("newspulse.runner.news_runner.run_render_stage", return_value=render_result) as run_render,
            patch("newspulse.runner.news_runner.run_delivery_stage") as run_delivery,
        ):
            runner._execute_mode_strategy(runner._get_mode_strategy(), schedule=schedule)

        self.assertFalse(run_render.call_args.kwargs["emit_notification"])
        self.assertFalse(run_delivery.called)
        self.assertEqual(scheduler.recorded, [])

    def test_daily_notifiable_content_requires_selection_filtered_new_items(self):
        runner = NewsRunner.__new__(NewsRunner)
        itemless_settings = SimpleNamespace()
        runner.settings = itemless_settings
        report_package = ReportPackage(
            meta=ReportPackageMeta(mode="daily", report_type="日报"),
            content=ReportContent(
                hotlist_groups=[],
                selected_items=[],
                new_items=[],
                standalone_sections=[],
                insight_sections=[],
            ),
            integrity=ReportIntegrity(valid=True),
        )

        self.assertFalse(runner._has_valid_content(report_package))

    def test_has_valid_content_requires_valid_report_package(self):
        runner = NewsRunner.__new__(NewsRunner)
        item = HotlistItem(
            news_item_id="1",
            source_id="hackernews",
            source_name="Hacker News",
            title="OpenAI launches a new coding agent",
            current_rank=1,
            ranks=[1],
        )
        report_package = ReportPackage(
            meta=ReportPackageMeta(mode="current", report_type="实时报告"),
            content=ReportContent(
                hotlist_groups=[SelectionGroup(key="ai", label="AI", items=[item], position=0)],
                selected_items=[item],
                new_items=[],
                standalone_sections=[],
                insight_sections=[],
            ),
            integrity=ReportIntegrity(valid=False, errors=["selection mismatch"]),
        )

        self.assertFalse(runner._has_valid_content(report_package))


if __name__ == "__main__":
    unittest.main()
