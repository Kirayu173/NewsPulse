import json
import shutil
import textwrap
import unittest
import uuid
from pathlib import Path

from newspulse.context import AppContext
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.contracts import SelectionResult


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


def _write_selection_configs(config_root: Path) -> None:
    _write_text(
        config_root / "custom" / "keyword" / "topics.txt",
        """
        [GLOBAL_FILTER]
        sports
        """,
    )
    _write_text(
        config_root / "ai_filter" / "prompt.txt",
        """
        [user]
        关注面:
        {interests_content}
        主题:
        {focus_topics}
        新闻:
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


def _build_config(config_root: Path, output_dir: Path) -> dict:
    return {
        "TIMEZONE": "Asia/Shanghai",
        "RANK_THRESHOLD": 5,
        "WEIGHT_CONFIG": {
            "RANK_WEIGHT": 0.6,
            "FREQUENCY_WEIGHT": 0.3,
            "HOTNESS_WEIGHT": 0.1,
        },
        "PLATFORMS": [{"id": "hackernews", "name": "Hacker News"}],
        "DISPLAY_MODE": "keyword",
        "DISPLAY": {
            "REGION_ORDER": ["hotlist", "new_items", "standalone", "insight"],
            "REGIONS": {"NEW_ITEMS": True},
            "STANDALONE": {"PLATFORMS": [], "MAX_ITEMS": 20},
        },
        "FILTER": {"METHOD": "keyword", "PRIORITY_SORT_ENABLED": True},
        "AI": {"MODEL": "openai/base", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER_MODEL": {"MODEL": "openai/filter", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER": {
            "BATCH_SIZE": 2,
            "BATCH_INTERVAL": 0,
            "MIN_SCORE": 0.8,
            "PROMPT_FILE": "prompt.txt",
            "EXTRACT_PROMPT_FILE": "extract_prompt.txt",
            "UPDATE_TAGS_PROMPT_FILE": "update_tags_prompt.txt",
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


def _seed_hotlist(ctx: AppContext) -> None:
    date_str = ctx.format_date()
    crawl_time = f"{date_str} 10:00:00"
    ctx.get_storage_manager().save_news_data(
        NewsData(
            date=date_str,
            crawl_time=crawl_time,
            items={
                "hackernews": [
                    NewsItem(
                        title="OpenAI launches a new coding agent",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=1,
                        url="https://example.com/openai",
                        mobile_url="https://m.example.com/openai",
                        crawl_time=crawl_time,
                        ranks=[1],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                    NewsItem(
                        title="GitHub releases a new open source tool",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=2,
                        url="https://example.com/github",
                        mobile_url="https://m.example.com/github",
                        crawl_time=crawl_time,
                        ranks=[2],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                    NewsItem(
                        title="Startup raises new funding round",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=3,
                        url="https://example.com/startup",
                        mobile_url="https://m.example.com/startup",
                        crawl_time=crawl_time,
                        ranks=[3],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                    NewsItem(
                        title="Sports finals preview",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=4,
                        url="https://example.com/sports",
                        mobile_url="https://m.example.com/sports",
                        crawl_time=crawl_time,
                        ranks=[4],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                ]
            },
            id_to_name={"hackernews": "Hacker News"},
            failed_ids=[],
        )
    )


class DeterministicQualityAIClient:
    def __init__(self):
        self.classify_calls = 0

    def chat(self, messages, **kwargs):
        self.classify_calls += 1
        results = []
        for line in messages[-1]["content"].splitlines():
            if not line[:1].isdigit() or ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            lowered = line.lower()
            if "openai" in lowered or "agent" in lowered:
                results.append({"id": prompt_id, "keep": True, "score": 0.96, "reasons": ["信息增量"], "evidence": "agent launch"})
            elif "github" in lowered or "open source" in lowered:
                results.append({"id": prompt_id, "keep": True, "score": 0.91, "reasons": ["开源发布"], "evidence": "open source release"})
            elif "startup" in lowered:
                results.append({"id": prompt_id, "keep": True, "score": 0.87, "reasons": ["创业动态"], "evidence": "funding"})
            else:
                results.append({"id": prompt_id, "keep": False, "score": 0.1, "reasons": ["低价值"], "evidence": "drop"})
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
            if "agent" in lowered or "openai" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "open source" in lowered or "github" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            elif "startup" in lowered or "funding" in lowered:
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([1.0, 1.0, 1.0])
        return vectors


class FailingAIClient:
    def chat(self, messages, **kwargs):
        raise RuntimeError("boom")


class AppContextSelectionStageTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "context-selection"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _create_context(self, root: Path) -> AppContext:
        config_root = root / "config"
        output_dir = root / "output"
        _write_selection_configs(config_root)
        _write_text(
            config_root / "custom" / "ai" / "ai.txt",
            """
            [TOPIC_CATALOG]

            [AI Agents]
            AI coding agents and MCP tooling
            + agent
            + OpenAI
            @priority: 1

            [Open Source]
            Open source tools and repo launches
            + GitHub
            + open source
            @priority: 2
            """,
        )
        _write_text(
            config_root / "custom" / "ai" / "startup.txt",
            """
            [TOPIC_CATALOG]

            [Startups]
            Startup launches and fundraising
            + startup
            + funding
            @priority: 1
            """,
        )
        ctx = AppContext(_build_config(config_root, output_dir))
        ctx._storage_manager = get_storage_manager(
            backend_type="local",
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=False,
            timezone=ctx.timezone,
            force_new=True,
        )
        return ctx

    def _build_ai_selection_service(self, ctx: AppContext, client) -> SelectionService:
        ai_strategy = AISelectionStrategy(
            storage_manager=ctx.get_storage_manager(),
            client=client,
            embedding_client=FakeEmbeddingClient(),
            filter_config=ctx.ai_filter_config,
            config_root=ctx.config_root,
            sleep_func=lambda _: None,
        )
        return SelectionService(
            config_root=str(ctx.config_root),
            rank_threshold=ctx.rank_threshold,
            weight_config=ctx.weight_config,
            max_news_per_keyword=ctx.config.get("MAX_NEWS_PER_KEYWORD", 0),
            sort_by_position_first=ctx.config.get("SORT_BY_POSITION_FIRST", False),
            ai_strategy=ai_strategy,
        )

    def test_keyword_and_ai_selection_stage_both_return_selection_result(self):
        tmpdir = self._create_workspace_tmpdir()
        ctx = self._create_context(tmpdir)
        try:
            _seed_hotlist(ctx)

            _, keyword_selection = ctx.run_selection_stage(
                mode="current",
                strategy="keyword",
                frequency_file="topics.txt",
            )

            ai_service = self._build_ai_selection_service(ctx, DeterministicQualityAIClient())
            _, ai_selection = ctx.run_selection_stage(
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="ai.txt",
                selection_service=ai_service,
            )

            self.assertIsInstance(keyword_selection, SelectionResult)
            self.assertIsInstance(ai_selection, SelectionResult)
            self.assertEqual(keyword_selection.strategy, "keyword")
            self.assertEqual(ai_selection.strategy, "ai")
            self.assertEqual(keyword_selection.total_selected, 3)
            self.assertEqual(ai_selection.total_selected, 2)
            self.assertEqual(ai_selection.diagnostics["rule_rejected_count"], 1)
        finally:
            ctx.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_emits_funnel_diagnostics(self):
        tmpdir = self._create_workspace_tmpdir()
        ctx = self._create_context(tmpdir)
        try:
            _seed_hotlist(ctx)
            client = DeterministicQualityAIClient()
            ai_service = self._build_ai_selection_service(ctx, client)

            _, result = ctx.run_selection_stage(
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="ai.txt",
                selection_service=ai_service,
            )

            self.assertEqual(result.diagnostics["batch_size"], 2)
            self.assertEqual(result.diagnostics["min_score"], 0.8)
            self.assertEqual(result.diagnostics["focus_labels"], ["AI Agents", "Open Source"])
            self.assertEqual(result.diagnostics["semantic_passed_count"], 2)
            self.assertEqual(result.diagnostics["llm_decision_count"], 2)
            self.assertGreater(client.classify_calls, 0)
        finally:
            ctx.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_supports_switching_interests_files(self):
        tmpdir = self._create_workspace_tmpdir()
        ctx = self._create_context(tmpdir)
        try:
            _seed_hotlist(ctx)
            ai_service = self._build_ai_selection_service(ctx, DeterministicQualityAIClient())
            _, first_result = ctx.run_selection_stage(
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="ai.txt",
                selection_service=ai_service,
            )
            _, second_result = ctx.run_selection_stage(
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="startup.txt",
                selection_service=ai_service,
            )

            self.assertEqual(first_result.diagnostics["interests_file"], "ai.txt")
            self.assertEqual(second_result.diagnostics["interests_file"], "startup.txt")
            self.assertEqual(first_result.diagnostics["focus_labels"], ["AI Agents", "Open Source"])
            self.assertEqual(second_result.diagnostics["focus_labels"], ["Startups"])
            self.assertEqual(second_result.total_selected, 1)
        finally:
            ctx.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_falls_back_to_keyword_when_ai_fails(self):
        tmpdir = self._create_workspace_tmpdir()
        ctx = self._create_context(tmpdir)
        try:
            _seed_hotlist(ctx)
            failing_service = self._build_ai_selection_service(ctx, FailingAIClient())

            _, result = ctx.run_selection_stage(
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="missing.txt",
                selection_service=failing_service,
            )

            self.assertEqual(result.strategy, "keyword")
            self.assertEqual(result.diagnostics["requested_strategy"], "ai")
            self.assertEqual(result.diagnostics["fallback_strategy"], "keyword")
            self.assertIn("ValueError", result.diagnostics["fallback_reason"])
        finally:
            ctx.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
