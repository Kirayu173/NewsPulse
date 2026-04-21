import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.context import AppContext
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.delivery import DeliveryService, GenericWebhookDeliveryAdapter
from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.models import InsightContentPayload, InsightItemAnalysis, ReducedContentBundle
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import InsightSection


def _today_at(ctx: AppContext, time_text: str) -> str:
    return f"{ctx.format_date()} {time_text}"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


def _write_config_files(config_root: Path) -> None:
    _write_text(
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
    _write_text(
        config_root / "custom" / "ai" / "interests.txt",
        """
        AI agents and coding tools
        startup launches
        """,
    )
    _write_text(
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
    _write_text(
        config_root / "ai_filter" / "extract_prompt.txt",
        """
        [user]
        INTERESTS:
        {interests_content}
        """,
    )
    _write_text(
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
            "PROMPT_FILE": "ai_analysis_prompt.txt",
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
    def chat(self, messages, **kwargs):
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
        return json.dumps(results)


class FakeEmbeddingClient:
    class _Config:
        model = "openai/embedding-test"

    config = _Config()

    def is_enabled(self):
        return True

    def embed_texts(self, texts, **kwargs):
        vectors = []
        for text in texts:
            lowered = str(text).lower()
            if "selection focus" in lowered or "ai agents" in lowered or "startup launches" in lowered:
                vectors.append([1.0, 1.0, 0.0])
            elif "openai" in lowered or "agent" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "startup" in lowered or "productivity" in lowered or "launch" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class StubInsightFetcher:
    def fetch_many(self, contexts):
        return [
            InsightContentPayload(
                news_item_id=context.news_item_id,
                status="ok",
                source_type=context.source_context.source_kind or "article",
                title=context.title,
                excerpt=context.source_context.summary,
                content_text=f"{context.title} -- enriched content",
                content_markdown=f"{context.title} -- enriched content",
                extractor_name="stub_fetcher",
            )
            for context in contexts
        ]


class StubInsightReducer:
    def reduce_many(self, contexts, payloads):
        return [
            ReducedContentBundle(
                news_item_id=context.news_item_id,
                status="ok",
                anchor_text=context.title,
                reduced_text=f"{context.title} -- reduced content",
                selected_sentences=(f"{context.title} -- reduced content",),
                evidence_sentences=(f"{context.title} -- reduced evidence",),
                reducer_name="stub_reducer",
            )
            for context in contexts
        ]


class StubInsightAnalyzer:
    def analyze_many(self, contexts, bundles):
        return [
            InsightItemAnalysis(
                news_item_id=context.news_item_id,
                title=context.title,
                what_happened=f"{context.title} happened",
                why_it_matters=f"{context.title} matters",
                evidence=(f"{context.title} evidence",),
                diagnostics={"status": "ok"},
            )
            for context in contexts
        ]


class StubInsightAggregate:
    def generate(self, item_analyses, contexts):
        return (
            [
                InsightSection(
                    key="core_trends",
                    title="Core Trends",
                    content="AI tools keep dominating the developer conversation.",
                    metadata={
                        "supporting_news_ids": [analysis.news_item_id for analysis in item_analyses],
                    },
                )
            ],
            '{"sections": []}',
            {"item_count": len(item_analyses), "section_count": 1},
        )


class RecordingSender:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return True


class NativeWorkflowEndToEndTest(unittest.TestCase):
    def _create_context(
        self,
        tmp: str,
        *,
        selection_strategy: str = "keyword",
        ai_analysis_enabled: bool = False,
    ) -> AppContext:
        root = Path(tmp)
        config_root = root / "config"
        output_dir = root / "output"
        _write_config_files(config_root)
        ctx = AppContext(
            _build_config(
                config_root,
                output_dir,
                selection_strategy=selection_strategy,
                ai_analysis_enabled=ai_analysis_enabled,
            )
        )
        ctx._storage_manager = get_storage_manager(
            backend_type="local",
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=True,
            timezone=ctx.timezone,
            force_new=True,
        )
        return ctx

    def _seed_hotlist(self, ctx: AppContext) -> None:
        ctx.get_storage_manager().save_news_data(
            NewsData(
                date=ctx.format_date(),
                crawl_time=_today_at(ctx, "10:00:00"),
                items={
                    "hackernews": [
                        NewsItem(
                            title="OpenAI launches a new coding agent",
                            source_id="hackernews",
                            source_name="Hacker News",
                            rank=1,
                            url="https://example.com/openai",
                            mobile_url="https://m.example.com/openai",
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[1],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
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
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[3],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
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
                            crawl_time=_today_at(ctx, "10:00:00"),
                            ranks=[2],
                            first_time=_today_at(ctx, "10:00:00"),
                            last_time=_today_at(ctx, "10:00:00"),
                            count=1,
                            rank_timeline=[{"time": "10:00", "rank": 2}],
                        )
                    ],
                },
                id_to_name={"hackernews": "Hacker News", "producthunt": "Product Hunt"},
                failed_ids=[],
            )
        )

    def _build_ai_selection_service(self, ctx: AppContext) -> SelectionService:
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
            storage_manager=ctx.get_storage_manager(),
            client=RoutingAISelectionClient(),
            embedding_client=FakeEmbeddingClient(),
            filter_config=ctx.ai_filter_config,
            config_root=ctx.config_root,
            sleep_func=lambda _: None,
            classify_prompt=classify_prompt,
        )
        return SelectionService(
            config_root=str(ctx.config_root),
            rank_threshold=ctx.rank_threshold,
            weight_config=ctx.weight_config,
            max_news_per_keyword=ctx.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=ctx.config.get("SORT_BY_POSITION_FIRST", False),
            ai_strategy=ai_strategy,
        )

    def _build_ai_insight_service(self, ctx: AppContext) -> InsightService:
        return InsightService(
            ai_strategy=AIInsightStrategy(
                client=object(),
                analysis_config=ctx.config["AI_ANALYSIS"],
                content_fetcher=StubInsightFetcher(),
                content_reducer=StubInsightReducer(),
                item_analyzer=StubInsightAnalyzer(),
                aggregate_generator=StubInsightAggregate(),
            )
        )

    def _build_delivery_service(self, ctx: AppContext, sender: RecordingSender) -> DeliveryService:
        return DeliveryService(
            generic_webhook_adapter=GenericWebhookDeliveryAdapter(ctx.config, sender_func=sender)
        )

    def _run_pipeline(
        self,
        ctx: AppContext,
        *,
        selection_strategy: str,
        selection_service: SelectionService | None = None,
        insight_service: InsightService | None = None,
        delivery_service: DeliveryService | None = None,
    ):
        snapshot, selection = ctx.run_selection_stage(
            mode="daily",
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            selection_service=selection_service,
        )
        insight = ctx.run_insight_stage(
            report_mode="daily",
            snapshot=snapshot,
            selection=selection,
            strategy=selection_strategy,
            frequency_file="topics.txt",
            interests_file="interests.txt" if selection_strategy == "ai" else None,
            insight_service=insight_service,
        )
        report_package = ctx.assemble_report_package(snapshot, selection, insight)
        render_result = ctx.run_render_stage(report_package, emit_html=True, emit_notification=True)
        delivery_result = ctx.run_delivery_stage(render_result.payloads, delivery_service=delivery_service)
        return snapshot, selection, insight, report_package, render_result, delivery_result

    def test_end_to_end_runs_with_all_ai_disabled(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, report_package, render_result, delivery_result = self._run_pipeline(
                    ctx,
                    selection_strategy="keyword",
                    delivery_service=self._build_delivery_service(ctx, sender),
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
                ctx.cleanup()

    def test_end_to_end_supports_ai_selection_only(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp, selection_strategy="ai")
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, report_package, render_result, _ = self._run_pipeline(
                    ctx,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(ctx),
                    delivery_service=self._build_delivery_service(ctx, sender),
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
                ctx.cleanup()

    def test_end_to_end_supports_ai_selection_and_insight(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp, selection_strategy="ai", ai_analysis_enabled=True)
            sender = RecordingSender()
            try:
                self._seed_hotlist(ctx)
                _, selection, insight, report_package, render_result, delivery_result = self._run_pipeline(
                    ctx,
                    selection_strategy="ai",
                    selection_service=self._build_ai_selection_service(ctx),
                    insight_service=self._build_ai_insight_service(ctx),
                    delivery_service=self._build_delivery_service(ctx, sender),
                )

                joined_payload = "\n".join(payload.content for payload in render_result.payloads)
                self.assertEqual(selection.strategy, "ai")
                self.assertTrue(insight.enabled)
                self.assertEqual(insight.diagnostics["analyzed_items"], 2)
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
                ctx.cleanup()


if __name__ == "__main__":
    unittest.main()
