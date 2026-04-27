import shutil
import unittest
import uuid
from pathlib import Path

from newspulse.runtime import RuntimeProviders, build_runtime, run_selection_stage
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.contracts import SelectionResult
from tests.helpers.io import write_text
from tests.helpers.selection import DeterministicQualityAIClient, FakeEmbeddingClient


def _write_selection_configs(config_root: Path) -> None:
    write_text(
        config_root / "rules" / "keyword" / "topics.txt",
        """
        [GLOBAL_FILTER]
        sports
        """,
    )
    write_text(
        config_root / "prompts" / "selection" / "classify.txt",
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
    write_text(
        config_root / "prompts" / "selection" / "extract_tags.txt",
        """
        [user]
        INTERESTS:
        {interests_content}
        """,
    )
    write_text(
        config_root / "prompts" / "selection" / "update_tags.txt",
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
            "INTERESTS_FILE": "ai.txt",
            "BATCH_SIZE": 2,
            "BATCH_INTERVAL": 0,
            "MIN_SCORE": 0.8,
            "PROMPT_FILE": "prompts/selection/classify.txt",
            "EXTRACT_PROMPT_FILE": "prompts/selection/extract_tags.txt",
            "UPDATE_TAGS_PROMPT_FILE": "prompts/selection/update_tags.txt",
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


def _seed_hotlist(runtime) -> None:
    date_str = runtime.settings.format_date()
    crawl_time = f"{date_str} 10:00:00"
    runtime.container.storage().save_news_data(
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


class FailingAIClient:
    def generate_json(self, messages, **kwargs):
        raise RuntimeError("boom")


class RuntimeSelectionStageTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "context-selection"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _create_runtime(self, root: Path):
        config_root = root / "config"
        output_dir = root / "output"
        _write_selection_configs(config_root)
        write_text(
            config_root / "profiles" / "ai" / "ai.txt",
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
        write_text(
            config_root / "profiles" / "ai" / "startup.txt",
            """
            [TOPIC_CATALOG]

            [Startups]
            Startup launches and fundraising
            + startup
            + funding
            @priority: 1
            """,
        )
        storage = get_storage_manager(
            backend_type="local",
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=False,
            timezone="Asia/Shanghai",
        )
        return build_runtime(
            _build_config(config_root, output_dir),
            providers=RuntimeProviders(storage_factory=lambda settings: storage),
        )

    def _make_quality_client(self) -> DeterministicQualityAIClient:
        return DeterministicQualityAIClient(
            rules=[
                {
                    "contains": ("openai", "agent"),
                    "keep": True,
                    "score": 0.96,
                    "reasons": ["信息增量"],
                    "evidence": "agent launch",
                    "matched_topics": ["AI Agents"],
                },
                {
                    "contains": ("github", "open source"),
                    "keep": True,
                    "score": 0.91,
                    "reasons": ["开源发布"],
                    "evidence": "open source release",
                    "matched_topics": ["Open Source"],
                },
                {
                    "contains": ("startup", "funding"),
                    "keep": True,
                    "score": 0.87,
                    "reasons": ["创业动态"],
                    "evidence": "funding",
                    "matched_topics": ["Startups"],
                },
            ],
            default_decision={
                "keep": False,
                "score": 0.1,
                "reasons": ["低价值"],
                "evidence": "drop",
                "matched_topics": [],
            },
        )

    def _make_embedding_client(self) -> FakeEmbeddingClient:
        return FakeEmbeddingClient(
            groups=[
                (("agent", "openai"), (1.0, 0.0, 0.0)),
                (("open source", "github"), (0.0, 1.0, 0.0)),
                (("startup", "funding"), (0.0, 0.0, 1.0)),
            ],
            default_vector=(1.0, 1.0, 1.0),
        )

    def _build_ai_selection_service(self, runtime, client) -> SelectionService:
        settings = runtime.settings
        ai_strategy = AISelectionStrategy(
            storage_manager=runtime.container.storage(),
            client=client,
            embedding_client=self._make_embedding_client(),
            filter_config=settings.selection.filter_config,
            config_root=settings.paths.config_root,
            sleep_func=lambda _: None,
        )
        return SelectionService(
            config_root=str(settings.paths.config_root),
            rank_threshold=settings.selection.rank_threshold,
            weight_config=settings.selection.weight_config,
            max_news_per_keyword=settings.selection.max_news_per_keyword,
            sort_by_position_first=settings.selection.sort_by_position_first,
            ai_strategy=ai_strategy,
        )

    def test_keyword_and_ai_selection_stage_both_return_selection_result(self):
        tmpdir = self._create_workspace_tmpdir()
        runtime = self._create_runtime(tmpdir)
        try:
            _seed_hotlist(runtime)

            _, keyword_selection = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
                mode="current",
                strategy="keyword",
                frequency_file="topics.txt",
            )

            ai_service = self._build_ai_selection_service(runtime, self._make_quality_client())
            _, ai_selection = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
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
            runtime.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_emits_funnel_diagnostics(self):
        tmpdir = self._create_workspace_tmpdir()
        runtime = self._create_runtime(tmpdir)
        try:
            _seed_hotlist(runtime)
            client = self._make_quality_client()
            ai_service = self._build_ai_selection_service(runtime, client)

            _, result = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
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
            runtime.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_supports_switching_interests_files(self):
        tmpdir = self._create_workspace_tmpdir()
        runtime = self._create_runtime(tmpdir)
        try:
            _seed_hotlist(runtime)
            ai_service = self._build_ai_selection_service(runtime, self._make_quality_client())
            _, first_result = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
                mode="current",
                strategy="ai",
                frequency_file="topics.txt",
                interests_file="ai.txt",
                selection_service=ai_service,
            )
            _, second_result = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
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
            runtime.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_selection_stage_falls_back_to_keyword_when_ai_fails(self):
        tmpdir = self._create_workspace_tmpdir()
        runtime = self._create_runtime(tmpdir)
        try:
            _seed_hotlist(runtime)
            failing_service = self._build_ai_selection_service(runtime, FailingAIClient())

            _, result = run_selection_stage(
                runtime.settings,
                runtime.container,
                runtime.selection_builder,
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
            runtime.cleanup()
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
