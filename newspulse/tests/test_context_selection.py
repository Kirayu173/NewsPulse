import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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
        [WORD_GROUPS]
        [AI]
        OpenAI
        agent

        [OpenSource]
        GitHub
        open source
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
            "REGION_ORDER": ["hotlist", "new_items", "standalone", "ai_analysis"],
            "REGIONS": {"NEW_ITEMS": True},
            "STANDALONE": {"PLATFORMS": [], "MAX_ITEMS": 20},
        },
        "FILTER": {"METHOD": "keyword", "PRIORITY_SORT_ENABLED": True},
        "AI": {"MODEL": "openai/base", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_FILTER_MODEL": {"MODEL": "openai/filter", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_ANALYSIS_MODEL": {"MODEL": "openai/analysis", "API_KEY": "test-key", "TIMEOUT": 30},
        "AI_TRANSLATION_MODEL": {"MODEL": "openai/translation", "API_KEY": "test-key", "TIMEOUT": 30},
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
                        title="Product Hunt startup launch roundup",
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
                ]
            },
            id_to_name={"hackernews": "Hacker News"},
            failed_ids=[],
        )
    )


class RoutingAIClient:
    def __init__(self):
        self.classify_calls = 0

    def chat(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        if user_content.startswith("INTERESTS:"):
            lowered = user_content.lower()
            if "startup" in lowered:
                return json.dumps({"tags": [{"tag": "Startups", "description": "startup launches"}]})
            return json.dumps(
                {
                    "tags": [
                        {"tag": "AI Agents", "description": "AI coding agents"},
                        {"tag": "Open Source", "description": "open source tools"},
                    ]
                }
            )

        if user_content.startswith("OLD:"):
            return json.dumps(
                {
                    "keep": [{"tag": "AI Agents", "description": "AI coding agents"}],
                    "add": [{"tag": "Startups", "description": "startup launches"}],
                    "remove": ["Open Source"],
                    "change_ratio": 0.2,
                }
            )

        self.classify_calls += 1
        tag_ids = {}
        for line in user_content.splitlines():
            if ". " in line and ":" in line and "[" not in line:
                prefix, rest = line.split(". ", 1)
                if prefix.isdigit():
                    tag_name = rest.split(":", 1)[0].strip()
                    tag_ids[tag_name] = int(prefix)

        results = []
        for line in user_content.splitlines():
            if ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            lowered = line.lower()
            if "openai" in lowered or "agent" in lowered:
                results.append({"id": prompt_id, "tag_id": tag_ids.get("AI Agents", next(iter(tag_ids.values()))), "score": 0.96})
            elif "github" in lowered or "open source" in lowered:
                results.append({"id": prompt_id, "tag_id": tag_ids.get("Open Source", next(iter(tag_ids.values()))), "score": 0.91})
            elif "startup" in lowered:
                results.append({"id": prompt_id, "tag_id": tag_ids.get("Startups", next(iter(tag_ids.values()))), "score": 0.87})
        return json.dumps(results)


class FailingAIClient:
    def chat(self, messages, **kwargs):
        raise RuntimeError("boom")


class AppContextSelectionStageTest(unittest.TestCase):
    def _create_context(self, tmp: str) -> AppContext:
        root = Path(tmp)
        config_root = root / "config"
        output_dir = root / "output"
        _write_selection_configs(config_root)
        _write_text(config_root / "custom" / "ai" / "ai.txt", "AI agents\nopen source tools")
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
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            try:
                _seed_hotlist(ctx)

                _, keyword_selection = ctx.run_selection_stage(
                    mode="current",
                    strategy="keyword",
                    frequency_file="topics.txt",
                )

                ai_service = self._build_ai_selection_service(ctx, RoutingAIClient())
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
                self.assertTrue(keyword_selection.groups)
                self.assertTrue(ai_selection.groups)
            finally:
                ctx.cleanup()

    def test_run_selection_stage_passes_ai_options_and_skips_already_analyzed_news(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            try:
                _seed_hotlist(ctx)
                client = RoutingAIClient()
                ai_service = self._build_ai_selection_service(ctx, client)

                _, first_result = ctx.run_selection_stage(
                    mode="current",
                    strategy="ai",
                    interests_file="ai.txt",
                    selection_service=ai_service,
                )
                first_call_count = client.classify_calls

                _, second_result = ctx.run_selection_stage(
                    mode="current",
                    strategy="ai",
                    interests_file="ai.txt",
                    selection_service=ai_service,
                )

                self.assertEqual(first_result.diagnostics["batch_size"], 2)
                self.assertEqual(first_result.diagnostics["min_score"], 0.8)
                self.assertEqual(first_call_count, 2)
                self.assertEqual(client.classify_calls, first_call_count)
                self.assertEqual(second_result.diagnostics["pending_candidates"], 0)
            finally:
                ctx.cleanup()

    def test_run_selection_stage_supports_switching_interests_files(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            try:
                _seed_hotlist(ctx)
                config_root = Path(tmp) / "config"
                _write_text(config_root / "custom" / "ai" / "ai.txt", "AI agents\nopen source tools")
                _write_text(config_root / "custom" / "ai" / "startup.txt", "startup launches")

                ai_service = self._build_ai_selection_service(ctx, RoutingAIClient())
                _, first_result = ctx.run_selection_stage(
                    mode="current",
                    strategy="ai",
                    interests_file="ai.txt",
                    selection_service=ai_service,
                )
                _, second_result = ctx.run_selection_stage(
                    mode="current",
                    strategy="ai",
                    interests_file="startup.txt",
                    selection_service=ai_service,
                )

                self.assertEqual(first_result.diagnostics["interests_file"], "ai.txt")
                self.assertEqual(second_result.diagnostics["interests_file"], "startup.txt")
                self.assertTrue(ctx.get_storage_manager().get_active_ai_filter_tags(interests_file="ai.txt"))
                self.assertTrue(ctx.get_storage_manager().get_active_ai_filter_tags(interests_file="startup.txt"))
            finally:
                ctx.cleanup()

    def test_run_selection_stage_falls_back_to_keyword_when_ai_fails(self):
        with TemporaryDirectory() as tmp:
            ctx = self._create_context(tmp)
            try:
                _seed_hotlist(ctx)
                failing_service = self._build_ai_selection_service(ctx, FailingAIClient())

                _, result = ctx.run_selection_stage(
                    mode="current",
                    strategy="ai",
                    frequency_file="topics.txt",
                    interests_file="ai.txt",
                    selection_service=failing_service,
                )

                self.assertEqual(result.strategy, "keyword")
                self.assertEqual(result.diagnostics["requested_strategy"], "ai")
                self.assertEqual(result.diagnostics["fallback_strategy"], "keyword")
                self.assertIn("RuntimeError", result.diagnostics["fallback_reason"])
            finally:
                ctx.cleanup()


if __name__ == "__main__":
    unittest.main()
