import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from newspulse.storage.base import NewsData, NewsItem
from newspulse.storage.local import LocalStorageBackend
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.ai_classifier import _format_news_list
from newspulse.workflow.selection.models import AIBatchNewsItem
from newspulse.workflow.shared.contracts import HotlistItem
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.options import SelectionAIOptions, SelectionOptions, SelectionSemanticOptions, SnapshotOptions
from newspulse.workflow.snapshot.service import SnapshotService
from tests.helpers.io import write_text
from tests.helpers.runtime import json_result
from tests.helpers.selection import DeterministicQualityAIClient, FakeEmbeddingClient

TEST_TMPDIR = Path("tmp_test_work")
TEST_TMPDIR.mkdir(exist_ok=True)


TEST_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _today_str() -> str:
    return datetime.now(TEST_TIMEZONE).date().isoformat()


def _today_at(time_text: str) -> str:
    return f"{_today_str()} {time_text}"


def _make_tmp_dir() -> Path:
    path = TEST_TMPDIR / f"case-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_test_ai_config(config_root: Path) -> None:
    write_text(
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


def _build_storage(tmp: str) -> LocalStorageBackend:
    return LocalStorageBackend(
        data_dir=str(Path(tmp) / "output"),
        enable_txt=False,
        enable_html=False,
        timezone="Asia/Shanghai",
    )


def _seed_hotlist(storage: LocalStorageBackend) -> None:
    crawl_time = _today_at("10:00:00")
    storage.save_news_data(
        NewsData(
            date=_today_str(),
            crawl_time=crawl_time,
            items={
                "hackernews": [
                    NewsItem(
                        title="OpenAI launches coding agent",
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
                        title="GitHub ships a new open source CLI",
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
                        title="Beginner tutorial for AI resumes",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=3,
                        url="https://example.com/tutorial",
                        mobile_url="https://m.example.com/tutorial",
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


def _build_snapshot(storage: LocalStorageBackend):
    service = SnapshotService(
        storage,
        platform_ids=["hackernews"],
        platform_names={"hackernews": "Hacker News"},
    )
    return service.build(SnapshotOptions(mode="current"))


class SplitFallbackAIClient:
    def __init__(self):
        self.calls = []

    def generate_json(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        lines = [line for line in user_content.splitlines() if line[:1].isdigit() and ". [" in line]
        self.calls.append(len(lines))
        if len(lines) > 1:
            raise RuntimeError("split me")

        prompt_id = int(lines[0].split(".", 1)[0])
        return json_result(
            [{"id": prompt_id, "keep": True, "score": 0.9, "reasons": ["ok"], "evidence": "ok"}]
        )


class PartialResponseAIClient:
    def __init__(self):
        self.calls = []

    def generate_json(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        lines = [line for line in user_content.splitlines() if line[:1].isdigit() and ". [" in line]
        self.calls.append(len(lines))
        if not lines:
            return json_result([])

        first_prompt_id = int(lines[0].split(".", 1)[0])
        return json_result(
            [
                {
                    "id": first_prompt_id,
                    "keep": True,
                    "score": 0.88,
                    "reasons": ["ok"],
                    "evidence": "partial response",
                }
            ]
        )


class EmptyResponseAIClient:
    def generate_json(self, messages, **kwargs):
        raise AIResponseDecodeError("AI response does not contain JSON")


class DummyStorage:
    def begin_batch(self):
        pass

    def end_batch(self):
        pass


class AISelectionStrategyTest(unittest.TestCase):
    def test_service_runs_ai_strategy_as_quality_gate(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)
        write_text(
            config_root / "custom" / "ai" / "unit.txt",
            """
            [TOPIC_CATALOG]

            [AI Agent / MCP]
            AI agents and coding agents
            + AI agent
            + coding agent
            @priority: 1

            [开源发布 / GitHub / HN]
            Open source tooling and repo launches
            + GitHub
            + open source
            @priority: 2
            """,
        )
        write_text(
            config_root / "custom" / "keyword" / "selection.txt",
            """
            [GLOBAL_FILTER]
            tutorial
            """,
        )

        storage = _build_storage(str(tmp_root))
        try:
            _seed_hotlist(storage)
            snapshot = _build_snapshot(storage)
            client = DeterministicQualityAIClient()

            ai_strategy = AISelectionStrategy(
                storage_manager=storage,
                client=client,
                embedding_client=FakeEmbeddingClient(),
                filter_config={"PROMPT_FILE": "prompt.txt"},
                config_root=config_root,
                sleep_func=lambda _: None,
            )
            service = SelectionService(config_root=str(config_root), ai_strategy=ai_strategy)

            result = service.run(
                snapshot,
                SelectionOptions(
                    strategy="ai",
                    frequency_file="selection.txt",
                    ai=SelectionAIOptions(
                        interests_file="unit.txt",
                        batch_size=10,
                        batch_interval=0,
                        min_score=0.7,
                    ),
                    semantic=SelectionSemanticOptions(
                        enabled=True,
                        top_k=3,
                        min_score=0.55,
                        direct_threshold=0.95,
                    ),
                ),
            )

            self.assertEqual(result.strategy, "ai")
            self.assertEqual(
                [item.title for item in result.qualified_items],
                ["OpenAI launches coding agent", "GitHub ships a new open source CLI"],
            )
            self.assertEqual(len(result.rejected_items), 1)
            self.assertEqual(result.rejected_items[0].rejected_stage, "rule")
            self.assertEqual(client.classify_calls, 1)
            self.assertEqual(result.diagnostics["focus_topic_count"], 2)
            self.assertEqual(result.diagnostics["rule_rejected_count"], 1)
            self.assertEqual(result.diagnostics["semantic_passed_count"], 2)

            selected_matches = result.diagnostics["selected_matches"]
            self.assertEqual(
                [match["decision_layer"] for match in selected_matches],
                ["llm_quality_gate", "llm_quality_gate"],
            )
        finally:
            storage.cleanup()

    def test_ai_classify_batch_splits_failed_batch_until_single_item(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)

        client = SplitFallbackAIClient()
        strategy = AISelectionStrategy(
            storage_manager=DummyStorage(),
            client=client,
            filter_config={"PROMPT_FILE": "prompt.txt"},
            config_root=config_root,
            sleep_func=lambda _: None,
        )

        batch_items = [
            AIBatchNewsItem(prompt_id=1, news_item_id="1", title="a"),
            AIBatchNewsItem(prompt_id=2, news_item_id="2", title="b"),
            AIBatchNewsItem(prompt_id=3, news_item_id="3", title="c"),
            AIBatchNewsItem(prompt_id=4, news_item_id="4", title="d"),
        ]
        results = strategy.classify_batch(
            batch_items,
            interests_content="AI",
        )

        self.assertEqual([result.news_item_id for result in results], ["1", "2", "3", "4"])
        self.assertTrue(all(result.keep for result in results))
        self.assertEqual(client.calls[0], 4)
        self.assertIn(2, client.calls)
        self.assertIn(1, client.calls)

    def test_ai_classify_batch_recovers_missing_decisions_via_retry(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)

        client = PartialResponseAIClient()
        strategy = AISelectionStrategy(
            storage_manager=DummyStorage(),
            client=client,
            filter_config={"PROMPT_FILE": "prompt.txt"},
            config_root=config_root,
            sleep_func=lambda _: None,
        )

        batch_items = [
            AIBatchNewsItem(prompt_id=1, news_item_id="1", title="a"),
            AIBatchNewsItem(prompt_id=2, news_item_id="2", title="b"),
            AIBatchNewsItem(prompt_id=3, news_item_id="3", title="c"),
        ]
        results = strategy.classify_batch(
            batch_items,
            interests_content="AI",
        )

        self.assertEqual([result.news_item_id for result in results], ["1", "2", "3"])
        self.assertTrue(all(result.keep for result in results))
        self.assertEqual(client.calls[0], 3)
        self.assertEqual(client.calls.count(1), 2)

    def test_ai_batch_prompt_includes_summary_and_structured_context(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)

        strategy = AISelectionStrategy(
            storage_manager=DummyStorage(),
            client=DeterministicQualityAIClient(),
            filter_config={"PROMPT_FILE": "prompt.txt"},
            config_root=config_root,
            sleep_func=lambda _: None,
        )

        batch_items = strategy.classifier.build_batch_items(
            [
                HotlistItem(
                    news_item_id="42",
                    title="openai/openai-agents-python",
                    source_id="github-trending-today",
                    source_name="GitHub Trending",
                    summary="Official OpenAI Agents SDK for Python",
                    metadata={
                        "source_kind": "github_repository",
                        "github": {
                            "language": "Python",
                            "topics": ["openai", "agent", "sdk"],
                            "stars_today": 842,
                            "stars_total": 12345,
                        },
                    },
                )
            ]
        )

        rendered = _format_news_list(batch_items)

        self.assertIn("summary: Official OpenAI Agents SDK for Python", rendered)
        self.assertIn("language: Python", rendered)
        self.assertIn("topics: openai, agent, sdk", rendered)
        self.assertIn("stars_today: 842", rendered)

    def test_ai_strategy_uses_structured_topic_catalog_as_focus_topics(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)
        write_text(
            config_root / "custom" / "ai" / "catalog.txt",
            """
            [TOPIC_CATALOG]

            [AI Agent / MCP]
            AI Agent、MCP 与智能工作流工具
            + AI Agent
            + MCP
            @priority: 1

            [开源发布 / GitHub / HN]
            GitHub Trending、开源发布与仓库热点
            + GitHub
            + open source
            @priority: 2
            """,
        )

        storage = _build_storage(str(tmp_root))
        try:
            _seed_hotlist(storage)
            snapshot = _build_snapshot(storage)
            strategy = AISelectionStrategy(
                storage_manager=storage,
                client=DeterministicQualityAIClient(),
                embedding_client=FakeEmbeddingClient(),
                filter_config={"PROMPT_FILE": "prompt.txt"},
                config_root=config_root,
                sleep_func=lambda _: None,
            )

            result = strategy.run(
                snapshot,
                SelectionOptions(
                    strategy="ai",
                    ai=SelectionAIOptions(interests_file="catalog.txt", batch_size=10, batch_interval=0, min_score=0.7),
                    semantic=SelectionSemanticOptions(enabled=True, top_k=2, min_score=0.55, direct_threshold=0.95),
                ),
            )

            self.assertEqual(result.diagnostics["focus_topic_count"], 2)
            self.assertEqual(result.diagnostics["focus_labels"], ["AI Agent / MCP", "开源发布 / GitHub / HN"])
            self.assertEqual(result.diagnostics["semantic_topics"][0]["seed_keywords"][0], "AI Agent")
        finally:
            storage.cleanup()

    def test_ai_strategy_rejects_items_below_llm_threshold(self):
        class LowScoreClient:
            def generate_json(self, messages, **kwargs):
                return json_result(
                    [{"id": 1, "keep": True, "score": 0.5, "reasons": ["信息密度不足"], "evidence": "low"}]
                )

        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)
        write_text(config_root / "custom" / "ai" / "unit.txt", "AI agents")

        storage = _build_storage(str(tmp_root))
        try:
            _seed_hotlist(storage)
            snapshot = _build_snapshot(storage)
            # Only keep the first item in semantic stage to make the threshold assertion deterministic.
            snapshot.items = snapshot.items[:1]
            strategy = AISelectionStrategy(
                storage_manager=storage,
                client=LowScoreClient(),
                filter_config={"PROMPT_FILE": "prompt.txt"},
                config_root=config_root,
                sleep_func=lambda _: None,
            )

            result = strategy.run(
                snapshot,
                SelectionOptions(
                    strategy="ai",
                    ai=SelectionAIOptions(interests_file="unit.txt", batch_size=10, batch_interval=0, min_score=0.7),
                    semantic=SelectionSemanticOptions(enabled=False),
                ),
            )

            self.assertEqual(result.total_selected, 0)
            self.assertEqual(len(result.rejected_items), 1)
            self.assertEqual(result.rejected_items[0].rejected_stage, "llm")
            self.assertIn("quality score below threshold", result.rejected_items[0].rejected_reason)
        finally:
            storage.cleanup()

    def test_service_falls_back_to_keyword_when_llm_returns_empty_payload(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / "config"
        _write_test_ai_config(config_root)
        write_text(config_root / "custom" / "ai" / "unit.txt", "AI agents")

        storage = _build_storage(str(tmp_root))
        try:
            _seed_hotlist(storage)
            snapshot = _build_snapshot(storage)
            snapshot.items = snapshot.items[:1]
            service = SelectionService(
                config_root=str(config_root),
                ai_strategy=AISelectionStrategy(
                    storage_manager=storage,
                    client=EmptyResponseAIClient(),
                    filter_config={"PROMPT_FILE": "prompt.txt"},
                    config_root=config_root,
                    sleep_func=lambda _: None,
                ),
            )

            result = service.run(
                snapshot,
                SelectionOptions(
                    strategy="ai",
                    ai=SelectionAIOptions(interests_file="unit.txt", batch_size=1, batch_interval=0, min_score=0.7),
                    semantic=SelectionSemanticOptions(enabled=False),
                ),
            )

            self.assertEqual(result.strategy, "keyword")
            self.assertEqual(result.total_selected, 1)
            self.assertEqual(result.diagnostics["requested_strategy"], "ai")
            self.assertEqual(result.diagnostics["fallback_strategy"], "keyword")
            self.assertIn("AI response does not contain JSON", result.diagnostics["fallback_reason"])
        finally:
            storage.cleanup()


if __name__ == "__main__":
    unittest.main()
