import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from newspulse.context import AppContext
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


def _write_insight_configs(config_root: Path) -> None:
    _write_text(
        config_root / "custom" / "keyword" / "topics.txt",
        """
        [WORD_GROUPS]
        [AI]
        AI
        OpenAI
        agent

        [Startups]
        startup
        launch
        """,
    )
    _write_text(
        config_root / "ai_analysis_prompt.txt",
        """
        [user]
        MODE={report_mode}
        TYPE={report_type}
        COUNT={news_count}
        PLATFORMS={platforms}
        KEYWORDS={keywords}
        NEWS:
        {news_content}
        STANDALONE:
        {standalone_content}
        LANG={language}
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
    ai_mode: str = "follow_report",
    max_news: int = 50,
) -> dict:
    return {
        "TIMEZONE": "Asia/Shanghai",
        "RANK_THRESHOLD": 10,
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
            "REGION_ORDER": ["hotlist", "new_items", "standalone", "ai_analysis"],
            "REGIONS": {"NEW_ITEMS": True},
            "STANDALONE": {"PLATFORMS": ["producthunt"], "MAX_ITEMS": 10},
        },
        "FILTER": {"METHOD": "keyword", "PRIORITY_SORT_ENABLED": True},
        "AI": {"MODEL": "openai/base", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_TRANSLATION_MODEL": {"MODEL": "openai/translation", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER_MODEL": {"MODEL": "openai/filter", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER": {
            "BATCH_SIZE": 2,
            "BATCH_INTERVAL": 0,
            "MIN_SCORE": 0.8,
            "PROMPT_FILE": "prompt.txt",
            "EXTRACT_PROMPT_FILE": "extract_prompt.txt",
            "UPDATE_TAGS_PROMPT_FILE": "update_tags_prompt.txt",
        },
        "AI_ANALYSIS": {
            "ENABLED": True,
            "MODE": ai_mode,
            "MAX_NEWS_FOR_ANALYSIS": max_news,
            "INCLUDE_RANK_TIMELINE": True,
            "INCLUDE_STANDALONE": True,
            "LANGUAGE": "Chinese",
            "PROMPT_FILE": "ai_analysis_prompt.txt",
        },
        "STORAGE": {
            "BACKEND": "local",
            "FORMATS": {"TXT": False, "HTML": False},
            "LOCAL": {"DATA_DIR": str(output_dir), "RETENTION_DAYS": 0},
        },
        "MAX_NEWS_PER_KEYWORD": 0,
        "SORT_BY_POSITION_FIRST": False,
        "DEBUG": False,
        "_PATHS": {"CONFIG_ROOT": str(config_root)},
    }


def _build_context(tmp: str, *, ai_mode: str = "follow_report", max_news: int = 50) -> AppContext:
    root = Path(tmp)
    config_root = root / "config"
    output_dir = root / "output"
    _write_insight_configs(config_root)
    ctx = AppContext(_build_config(config_root, output_dir, ai_mode=ai_mode, max_news=max_news))
    ctx._storage_manager = get_storage_manager(
        backend_type="local",
        data_dir=str(output_dir),
        enable_txt=False,
        enable_html=False,
        timezone=ctx.timezone,
        force_new=True,
    )
    return ctx


def _save_crawl(ctx: AppContext, crawl_time: str, items: dict[str, list[NewsItem]]) -> None:
    ctx.get_storage_manager().save_news_data(
        NewsData(
            date="2026-04-17",
            crawl_time=crawl_time,
            items=items,
            id_to_name={"hackernews": "Hacker News", "producthunt": "Product Hunt"},
            failed_ids=[],
        )
    )


def _seed_single_crawl(ctx: AppContext) -> None:
    _save_crawl(
        ctx,
        "2026-04-17 10:00:00",
        {
            "hackernews": [
                NewsItem(
                    title="OpenAI launches a new coding agent",
                    source_id="hackernews",
                    source_name="Hacker News",
                    rank=1,
                    url="https://example.com/openai",
                    mobile_url="https://m.example.com/openai",
                    crawl_time="2026-04-17 10:00:00",
                    ranks=[1],
                    first_time="2026-04-17 10:00:00",
                    last_time="2026-04-17 10:00:00",
                    count=1,
                    rank_timeline=[{"time": "10:00", "rank": 1}],
                ),
            ],
            "producthunt": [
                NewsItem(
                    title="Startup launches a new AI productivity app",
                    source_id="producthunt",
                    source_name="Product Hunt",
                    rank=2,
                    url="https://example.com/startup",
                    mobile_url="https://m.example.com/startup",
                    crawl_time="2026-04-17 10:00:00",
                    ranks=[2],
                    first_time="2026-04-17 10:00:00",
                    last_time="2026-04-17 10:00:00",
                    count=1,
                    rank_timeline=[{"time": "10:00", "rank": 2}],
                ),
            ],
        },
    )


def _seed_two_crawls(ctx: AppContext) -> None:
    _save_crawl(
        ctx,
        "2026-04-17 09:00:00",
        {
            "hackernews": [
                NewsItem(
                    title="Morning AI launch roundup",
                    source_id="hackernews",
                    source_name="Hacker News",
                    rank=1,
                    url="https://example.com/morning",
                    mobile_url="https://m.example.com/morning",
                    crawl_time="2026-04-17 09:00:00",
                    ranks=[1],
                    first_time="2026-04-17 09:00:00",
                    last_time="2026-04-17 09:00:00",
                    count=1,
                    rank_timeline=[{"time": "09:00", "rank": 1}],
                ),
            ],
        },
    )
    _save_crawl(
        ctx,
        "2026-04-17 10:00:00",
        {
            "hackernews": [
                NewsItem(
                    title="Later AI agent release",
                    source_id="hackernews",
                    source_name="Hacker News",
                    rank=1,
                    url="https://example.com/later",
                    mobile_url="https://m.example.com/later",
                    crawl_time="2026-04-17 10:00:00",
                    ranks=[1],
                    first_time="2026-04-17 10:00:00",
                    last_time="2026-04-17 10:00:00",
                    count=1,
                    rank_timeline=[{"time": "10:00", "rank": 1}],
                ),
            ],
            "producthunt": [
                NewsItem(
                    title="Startup launch roundup",
                    source_id="producthunt",
                    source_name="Product Hunt",
                    rank=2,
                    url="https://example.com/roundup",
                    mobile_url="https://m.example.com/roundup",
                    crawl_time="2026-04-17 10:00:00",
                    ranks=[2],
                    first_time="2026-04-17 10:00:00",
                    last_time="2026-04-17 10:00:00",
                    count=1,
                    rank_timeline=[{"time": "10:00", "rank": 2}],
                ),
            ],
        },
    )


class CaptureInsightClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages[-1]["content"])
        return json.dumps(
            {
                "core_trends": "AI tools continue to dominate the hotlist.",
                "sentiment_controversy": "Developers are excited but still cautious.",
                "signals": "OpenAI and startup launches often appear together.",
                "outlook_strategy": "Keep tracking release cadence and user adoption.",
                "standalone_summaries": {
                    "Product Hunt": "Startup launches remain a strong secondary signal."
                },
            }
        )


def _build_insight_service(ctx: AppContext, client: CaptureInsightClient) -> InsightService:
    prompt_template = PromptTemplate(
        path=Path("test-ai-analysis-prompt.txt"),
        user_prompt=(
            "MODE={report_mode}\n"
            "TYPE={report_type}\n"
            "COUNT={news_count}\n"
            "PLATFORMS={platforms}\n"
            "KEYWORDS={keywords}\n"
            "NEWS:\n{news_content}\n"
            "STANDALONE:\n{standalone_content}\n"
            "LANG={language}"
        ),
    )
    return InsightService(
        ai_strategy=AIInsightStrategy(
            client=client,
            analysis_config=ctx.config["AI_ANALYSIS"],
            prompt_template=prompt_template,
        )
    )


class AppContextInsightStageTest(unittest.TestCase):
    def test_build_insight_options_uses_native_insight_config(self):
        with TemporaryDirectory() as tmp:
            ctx = _build_context(tmp, ai_mode="follow_report", max_news=7)
            try:
                options = ctx.build_insight_options(report_mode="current")

                self.assertTrue(options.enabled)
                self.assertEqual(options.strategy, "ai")
                self.assertEqual(options.mode, "current")
                self.assertEqual(options.max_items, 7)
                self.assertTrue(options.include_standalone)
                self.assertTrue(options.include_rank_timeline)
                self.assertEqual(options.metadata["requested_mode"], "follow_report")
            finally:
                ctx.cleanup()

    def test_run_insight_stage_returns_native_result_and_legacy_adapter_output(self):
        with TemporaryDirectory() as tmp:
            ctx = _build_context(tmp)
            try:
                _seed_single_crawl(ctx)
                snapshot, selection = ctx.run_selection_stage(
                    mode="current",
                    strategy="keyword",
                    frequency_file="topics.txt",
                )
                client = CaptureInsightClient()
                insight, legacy = ctx.run_insight_stage(
                    report_mode="current",
                    snapshot=snapshot,
                    selection=selection,
                    strategy="keyword",
                    frequency_file="topics.txt",
                    insight_service=_build_insight_service(ctx, client),
                )

                self.assertTrue(insight.enabled)
                self.assertEqual(legacy.ai_mode, "current")
                self.assertTrue(legacy.success)
                self.assertEqual(legacy.analyzed_news, 2)
                self.assertIn("Product Hunt", legacy.standalone_summaries)
                self.assertIn("OpenAI launches a new coding agent", client.calls[0])
                self.assertIn("Startup launches a new AI productivity app", client.calls[0])
            finally:
                ctx.cleanup()

    def test_run_insight_stage_rebuilds_selection_when_analysis_mode_differs(self):
        with TemporaryDirectory() as tmp:
            ctx = _build_context(tmp, ai_mode="daily")
            try:
                _seed_two_crawls(ctx)
                snapshot, selection = ctx.run_selection_stage(
                    mode="current",
                    strategy="keyword",
                    frequency_file="topics.txt",
                )
                self.assertEqual(selection.total_selected, 2)

                client = CaptureInsightClient()
                insight, legacy = ctx.run_insight_stage(
                    report_mode="current",
                    snapshot=snapshot,
                    selection=selection,
                    strategy="keyword",
                    frequency_file="topics.txt",
                    insight_service=_build_insight_service(ctx, client),
                )

                self.assertTrue(insight.enabled)
                self.assertEqual(legacy.ai_mode, "daily")
                self.assertEqual(legacy.analyzed_news, 3)
                self.assertIn("Morning AI launch roundup", client.calls[0])
                self.assertIn("Later AI agent release", client.calls[0])
            finally:
                ctx.cleanup()

    def test_run_insight_stage_respects_schedule_switches_and_once_recording(self):
        with TemporaryDirectory() as tmp:
            ctx = _build_context(tmp)
            try:
                _seed_single_crawl(ctx)
                snapshot, selection = ctx.run_selection_stage(
                    mode="current",
                    strategy="keyword",
                    frequency_file="topics.txt",
                )

                disabled_insight, disabled_legacy = ctx.run_insight_stage(
                    report_mode="current",
                    snapshot=snapshot,
                    selection=selection,
                    strategy="keyword",
                    frequency_file="topics.txt",
                    schedule=SimpleNamespace(analyze=False, once_analyze=False, period_key=None, period_name=None),
                )
                self.assertFalse(disabled_insight.enabled)
                self.assertIsNone(disabled_legacy)

                client = CaptureInsightClient()
                schedule = SimpleNamespace(
                    analyze=True,
                    once_analyze=True,
                    period_key="morning",
                    period_name="Morning",
                )
                _, legacy = ctx.run_insight_stage(
                    report_mode="current",
                    snapshot=snapshot,
                    selection=selection,
                    strategy="keyword",
                    frequency_file="topics.txt",
                    schedule=schedule,
                    insight_service=_build_insight_service(ctx, client),
                )

                self.assertTrue(legacy.success)
                self.assertTrue(ctx.get_storage_manager().has_period_executed(ctx.format_date(), "morning", "analyze"))
            finally:
                ctx.cleanup()


if __name__ == "__main__":
    unittest.main()
