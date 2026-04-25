import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from newspulse.runtime import (
    RuntimeProviders,
    assemble_report_package,
    build_runtime,
    run_delivery_stage,
    run_insight_stage,
    run_render_stage,
    run_selection_stage,
)
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.insight.summary_builder import InsightSummaryBuilder
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import InsightSection
from tests.helpers.io import write_text
from tests.helpers.runtime import json_result
from tests.helpers.selection import FakeEmbeddingClient

TEST_TMPDIR = Path(".tmp-test") / "workflow-end-to-end"
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_tmpdir():
    path = TEST_TMPDIR / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _today_at(runtime, time_text: str) -> str:
    return f"{runtime.settings.format_date()} {time_text}"


def _write_config_files(config_root: Path) -> None:
    write_text(
        config_root / "custom" / "keyword" / "topics.txt",
        """
        [WORD_GROUPS]
        [AI]
        OpenAI
        agent
        productivity

        [Startups]
        startup
        launch
        Product Hunt
        """,
    )
    write_text(
        config_root / "custom" / "ai" / "interests.txt",
        """
        AI agents and coding tools
        startup launches
        """,
    )
    write_text(
        config_root / "ai_filter" / "prompt.txt",
        """
        [user]
        TAGS:
        {tags_list}
        NEWS:
        {news_list}
        INTERESTS:
        {interests_content}
        """,
    )
    write_text(
        config_root / "ai_filter" / "extract_prompt.txt",
        """
        [user]
        INTERESTS:
        {interests_content}
        """,
    )
    write_text(
        config_root / "ai_filter" / "update_tags_prompt.txt",
        """
        [user]
        OLD:
        {old_tags_json}
        NEW:
        {interests_content}
        """,
    )


def _build_config(
    config_root: Path,
    output_dir: Path,
    *,
    selection_strategy: str = "keyword",
    ai_analysis_enabled: bool = False,
) -> dict:
    return {
        "TIMEZONE": "Asia/Shanghai",
        "RANK_THRESHOLD": 5,
        "WEIGHT_CONFIG": {
            "RANK_WEIGHT": 0.6,
            "FREQUENCY_WEIGHT": 0.3,
            "HOTNESS_WEIGHT": 0.1,
        },
        "PLATFORMS": [
            {"id": "hackernews", "name": "Hacker News"},
            {"id": "producthunt", "name": "Product Hunt"},
        ],
        "DISPLAY_MODE": "keyword",
        "DISPLAY": {
            "REGION_ORDER": ["hotlist", "new_items", "standalone", "insight"],
            "REGIONS": {
                "HOTLIST": True,
                "NEW_ITEMS": True,
                "STANDALONE": True,
                "INSIGHT": True,
            },
            "STANDALONE": {"PLATFORMS": ["producthunt"], "MAX_ITEMS": 10},
        },
        "FILTER": {
            "METHOD": selection_strategy,
            "FREQUENCY_FILE": "topics.txt",
            "PRIORITY_SORT_ENABLED": True,
        },
        "AI": {"MODEL": "openai/base", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER_MODEL": {"MODEL": "openai/filter", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER": {
            "INTERESTS_FILE": "interests.txt",
            "BATCH_SIZE": 2,
            "BATCH_INTERVAL": 0,
            "MIN_SCORE": 0.8,
            "FALLBACK_TO_KEYWORD": True,
        },
        "AI_ANALYSIS": {
            "ENABLED": ai_analysis_enabled,
            "STRATEGY": "ai" if ai_analysis_enabled else "noop",
            "MODE": "daily",
            "MAX_ITEMS": 5,
            "LANGUAGE": "Chinese",
            "PROMPT_FILE": "global_insight_prompt.txt",
        },
        "ENABLE_NOTIFICATION": True,
        "GENERIC_WEBHOOK_URL": "https://example.com/webhook",
        "GENERIC_WEBHOOK_TEMPLATE": "",
        "MESSAGE_BATCH_SIZE": 4000,
        "STORAGE": {
            "BACKEND": "local",
            "FORMATS": {"TXT": False, "HTML": True},
            "LOCAL": {"DATA_DIR": str(output_dir), "RETENTION_DAYS": 0},
        },
        "MAX_NEWS_PER_KEYWORD": 0,
        "SORT_BY_POSITION_FIRST": False,
        "SHOW_VERSION_UPDATE": False,
        "DEBUG": False,
        "_PATHS": {"CONFIG_ROOT": str(config_root)},
    }


class RoutingAISelectionClient:
    def generate_json(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        results = []
        for line in user_content.splitlines():
            if ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            lowered = line.lower()
            if "openai" in lowered or "agent" in lowered:
                results.append(
                    {
                        "id": prompt_id,
                        "keep": True,
                        "score": 0.96,
                        "reasons": ["high-signal ai tooling launch"],
                        "evidence": "OpenAI coding agent fits the quality gate.",
                        "matched_topics": ["AI agents and coding tools"],
                    }
                )
            elif "startup" in lowered or "productivity" in lowered:
                results.append(
                    {
                        "id": prompt_id,
                        "keep": True,
                        "score": 0.91,
                        "reasons": ["meaningful startup launch"],
                        "evidence": "A startup launch is still relevant for downstream analysis.",
                        "matched_topics": ["startup launches"],
                    }
                )
            else:
                results.append(
                    {
                        "id": prompt_id,
                        "keep": False,
                        "score": 0.05,
                        "reasons": ["off-topic sports item"],
                        "evidence": "The item is unrelated to the configured selection focus.",
                        "matched_topics": [],
                    }
                )
        return json_result(results)


class StubInsightAggregate:
    def generate(self, summary_bundle, contexts):
        item_ids = [
            item_id
            for summary in summary_bundle.item_summaries
            for item_id in summary.item_ids
        ]
        return (
            [
                InsightSection(
                    key="core_trends",
                    title="Core Trends",
                    content="AI tools keep dominating the developer conversation.",
                    metadata={
                        "supporting_news_ids": item_ids,
                    },
                )
            ],
            '{"sections": []}',
            {
                "summary_count": len(summary_bundle.summaries),
                "item_summary_count": len(summary_bundle.item_summaries),
                "theme_summary_count": len(summary_bundle.theme_summaries),
                "section_count": 1,
            },
        )


class RecordingSender:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True


class NativeWorkflowEndToEndTest(unittest.TestCase):
    @staticmethod
    def _build_embedding_client() -> FakeEmbeddingClient:
        return FakeEmbeddingClient(
            groups=[
                (("selection focus", "ai agents", "startup launches"), (1.0, 1.0, 0.0)),
                (("openai", "agent"), (1.0, 0.0, 0.0)),
                (("startup", "productivity", "launch"), (0.0, 1.0, 0.0)),
            ]
        )

    def _create_runtime(
        self,
        tmp: str,
        *,
        selection_strategy: str = "keyword",
        ai_analysis_enabled: bool = False,
    ):
        root = Path(tmp)
        config_root = root / "config"
        output_dir = root / "output"
        _write_config_files(config_root)
        storage = get_storage_manager(
            backend_type="local",
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=True,
            timezone="Asia/Shanghai",
        )
        return build_runtime(
            _build_config(
                config_root,
                output_dir,
                selection_strategy=selection_strategy,
                ai_analysis_enabled=ai_analysis_enabled,
            ),
            providers=RuntimeProviders(storage_factory=lambda settings: storage),
        )

    def _seed_hotlist(self, runtime) -> None:
        runtime.container.storage().save_news_data(
            NewsData(
                date=runtime.settings.format_date(),
                crawl_time=_today_at(runtime, "10:00:00"),
                items={
                    "hackernews": [
                        NewsItem(
                            title="OpenAI launches a new coding agent",
                            source_id="hackernews",
                            source_name="Hacker News",
                            rank=1,
                            url="https://example.com/openai",
                            mobile_url="https://m.example.com/openai",
                            crawl_time=_today_at(runtime, "10:00:00"),
                            ranks=[1],
                            first_time=_today_at(runtime, "10:00:00"),
                            last_time=_today_at(runtime, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 1}],
                        ),
                        NewsItem(
                            title="NBA finals schedule announced",
                            source_id="hackernews",
                            source_name="Hacker News",
                            rank=3,
                            url="https://example.com/nba",
                            mobile_url="https://m.example.com/nba",
                            crawl_time=_today_at(runtime, "10:00:00"),
                            ranks=[3],
                            first_time=_today_at(runtime, "10:00:00"),
                            last_time=_today_at(runtime, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 3}],
                        ),
                    ],
                    "producthunt": [
                        NewsItem(
                            title="Startup launches AI productivity app",
                            source_id="producthunt",
                            source_name="Product Hunt",
                            rank=2,
                            url="https://example.com/startup",
                            mobile_url="https://m.example.com/startup",
                            crawl_time=_today_at(runtime, "10:00:00"),
                            ranks=[2],
                            first_time=_today_at(runtime, "10:00:00"),
                            last_time=_today_at(runtime, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 2}],
                        )
                    ],
                },
                id_to_name={"hackernews": "Hacker News", "producthunt": "Product Hunt"},
                failed_ids=[],
            )
        )

    def _build_ai_selection_service(self, runtime) -> SelectionService:
        settings = runtime.settings
        classify_prompt = PromptTemplate(
            path=Path("selection-classify.txt"),
            user_prompt=(
                "INTERESTS:\n{interests_content}\n"
                "TOPICS:\n{focus_topics}\n"
                "NEWS_COUNT:\n{news_count}\n"
                "NEWS:\n{news_list}"
            ),
        )
        ai_strategy = AISelectionStrategy(
            storage_manager=runtime.container.storage(),
            client=RoutingAISelectionClient(),
            embedding_client=self._build_embedding_client(),
            filter_config=settings.selection.filter_config,
            config_root=settings.paths.config_root,
            sleep_func=lambda _: None,
            classify_prompt=classify_prompt,
        )
        return SelectionService(
            config_root=str(settings.paths.config_root),
            rank_threshold=settings.selection.rank_threshold,
            weight_config=settings.selection.weight_config,
            max_news_per_keyword=settings.selection.max_news_per_keyword,
            sort_by_position_first=settings.selection.sort_by_position_first,
            ai_strategy=ai_strategy,
        )

    def _build_ai_insight_service(self, runtime) -> InsightService:
        return InsightService(
            ai_strategy=AIInsightStrategy(
                client=object(),
                analysis_config=runtime.settings.insight.analysis_config,
                summary_builder=InsightSummaryBuilder(),
                aggregate_generator=StubInsightAggregate(),
            )
        )

    def _build_delivery_service(self, runtime, sender: RecordingSender) -> DeliveryService:
        return DeliveryService(
            generic_webhook_adapter=GenericWebhookDeliveryAdapter(runtime.settings.delivery.as_adapter_config(), sender_func=sender)
        )

    def _run_pipeline(
        self,
        runtime,
        *,
        selection_strategy: str,
        selection_service: SelectionService | None = None,
        insight_service: InsightService | None = None,
        delivery_service: DeliveryService | None = None,
    ):
        snapshot, selection = run_selection_stage(
            runtime.settings,
            runtime.container,
            runtime.selection_builder,
            mode="daily",
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            selection_service=selection_service,
        )
        insight = run_insight_stage(
            runtime.settings,
            runtime.container,
            runtime.selection_builder,
            runtime.insight_builder,
            report_mode="daily",
            snapshot=snapshot,
            selection=selection,
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            insight_service=insight_service,
        )
        report_package = assemble_report_package(runtime.container, snapshot, selection, insight)
        render_result = run_render_stage(runtime.container, runtime.render_builder, report_package, emit_html=True, emit_notification=True)
        delivery_result = run_delivery_stage(runtime.container, runtime.delivery_builder, render_result.payloads, delivery_service=delivery_service)
        return snapshot, selection, insight, report_package, render_result, delivery_result

    def test_end_to_end_runs_with_all_ai_disabled(self):
        with workspace_tmpdir() as tmp:
            runtime = self._create_runtime(tmp)
            sender = RecordingSender()
            try:
                self._seed_hotlist(runtime)
                _, selection, insight, report_package, render_result, delivery_result = self._run_pipeline(
                    runtime,
                    selection_strategy="keyword",
                    delivery_service=self._build_delivery_service(runtime, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "keyword")
                self.assertEqual(insight.strategy, "noop")
                self.assertEqual(report_package.meta.selection_strategy, "keyword")
                self.assertEqual(
                    [item.title for item in report_package.content.new_items],
                    [
                        "NBA finals schedule announced",
                        "OpenAI launches a new coding agent",
                        "Startup launches AI productivity app",
                    ],
                )
                self.assertIn("OpenAI launches a new coding agent", render_result.html.content)
                self.assertIn("NBA finals schedule announced", render_result.html.content)
                self.assertIn("OpenAI launches a new coding agent", joined_payload)
                self.assertIn("NBA finals schedule announced", joined_payload)
                self.assertTrue(delivery_result.success)
                self.assertTrue(sender.calls)
            finally:
                runtime.cleanup()

    def test_end_to_end_supports_ai_selection_only(self):
        with workspace_tmpdir() as tmp:
            runtime = self._create_runtime(tmp, selection_strategy="ai")
            sender = RecordingSender()
            try:
                self._seed_hotlist(runtime)
                _, selection, insight, report_package, render_result, _ = self._run_pipeline(
                    runtime,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(runtime),
                    delivery_service=self._build_delivery_service(runtime, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "ai")
                self.assertGreaterEqual(selection.total_selected, 2)
                self.assertEqual(insight.strategy, "noop")
                self.assertIn("OpenAI launches a new coding agent", joined_payload)
                self.assertNotIn("NBA finals schedule announced", joined_payload)
                self.assertEqual(
                    [item.title for item in report_package.content.new_items],
                    ["OpenAI launches a new coding agent", "Startup launches AI productivity app"],
                )
                self.assertNotIn("AI tools keep dominating the developer conversation.", joined_payload)
            finally:
                runtime.cleanup()

    def test_end_to_end_supports_ai_selection_and_insight(self):
        with workspace_tmpdir() as tmp:
            runtime = self._create_runtime(tmp, selection_strategy="ai", ai_analysis_enabled=True)
            sender = RecordingSender()
            try:
                self._seed_hotlist(runtime)
                _, selection, insight, report_package, render_result, delivery_result = self._run_pipeline(
                    runtime,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(runtime),
                    insight_service=self._build_ai_insight_service(runtime),
                    delivery_service=self._build_delivery_service(runtime, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "ai")
                self.assertTrue(insight.enabled)
                self.assertEqual(insight.diagnostics["item_summary_count"], 2)
                self.assertIn("AI tools keep dominating the developer conversation.", render_result.html.content)
                self.assertIn("AI tools keep dominating the developer conversation.", joined_payload)
                self.assertEqual(report_package.meta.insight_strategy, "ai")
                self.assertNotIn("NBA finals schedule announced", render_result.html.content)
                self.assertNotIn("NBA finals schedule announced", joined_payload)
                self.assertTrue(delivery_result.success)
                self.assertTrue(sender.calls)

                delivered_content = "\n".join(call["content"] for call in sender.calls)
                self.assertIn("OpenAI launches a new coding agent", delivered_content)
                self.assertIn("AI tools keep dominating the developer conversation.", delivered_content)
            finally:
                runtime.cleanup()


if __name__ == "__main__":
    unittest.main()
