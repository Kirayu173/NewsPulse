import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from newspulse.storage.base import NewsData, NewsItem
from newspulse.storage.local import LocalStorageBackend
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.models import AIActiveTag, AIBatchNewsItem
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.options import SelectionAIOptions, SelectionOptions, SnapshotOptions
from newspulse.workflow.snapshot.service import SnapshotService


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding="utf-8")


def _write_test_ai_config(config_root: Path) -> None:
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


def _build_storage(tmp: str) -> LocalStorageBackend:
    return LocalStorageBackend(
        data_dir=str(Path(tmp) / "output"),
        enable_txt=False,
        enable_html=False,
        timezone="Asia/Shanghai",
    )


def _seed_hotlist(storage: LocalStorageBackend) -> None:
    storage.save_news_data(
        NewsData(
            date="2026-04-17",
            crawl_time="2026-04-17 10:00:00",
            items={
                "hackernews": [
                    NewsItem(
                        title="OpenAI launches coding agent",
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
                    ),
                    NewsItem(
                        title="GitHub ships a new open source CLI",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=2,
                        url="https://example.com/github",
                        mobile_url="https://m.example.com/github",
                        crawl_time="2026-04-17 10:00:00",
                        ranks=[2],
                        first_time="2026-04-17 10:00:00",
                        last_time="2026-04-17 10:00:00",
                        count=1,
                    ),
                    NewsItem(
                        title="NBA finals preview",
                        source_id="hackernews",
                        source_name="Hacker News",
                        rank=3,
                        url="https://example.com/nba",
                        mobile_url="https://m.example.com/nba",
                        crawl_time="2026-04-17 10:00:00",
                        ranks=[3],
                        first_time="2026-04-17 10:00:00",
                        last_time="2026-04-17 10:00:00",
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


class DeterministicAIClient:
    def __init__(self):
        self.extract_calls = 0
        self.update_calls = 0
        self.classify_calls = 0

    def chat(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        if user_content.startswith("INTERESTS:"):
            self.extract_calls += 1
            return json.dumps(
                {
                    "tags": [
                        {"tag": "AI Agents", "description": "AI models and agents"},
                        {"tag": "Open Source", "description": "Open source tools"},
                    ]
                }
            )

        if user_content.startswith("OLD:"):
            self.update_calls += 1
            return json.dumps(
                {
                    "keep": [
                        {"tag": "AI Agents", "description": "AI agents and models"},
                    ],
                    "add": [
                        {"tag": "Startups", "description": "new startup launches"},
                    ],
                    "remove": ["Open Source"],
                    "change_ratio": 0.2,
                }
            )

        self.classify_calls += 1
        results = []
        for line in user_content.splitlines():
            if not line[:1].isdigit() or ". [" not in line:
                continue
            prompt_id = int(line.split(".", 1)[0])
            if "OpenAI launches" in line:
                results.append({"id": prompt_id, "tag_id": 1, "score": 0.96})
            elif "GitHub ships" in line:
                results.append({"id": prompt_id, "tag_id": 2, "score": 0.88})
        return json.dumps(results)


class SplitFallbackAIClient:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **kwargs):
        user_content = messages[-1]["content"]
        lines = [line for line in user_content.splitlines() if line[:1].isdigit() and ". " in line]
        self.calls.append(len(lines))
        if len(lines) > 1:
            raise RuntimeError("split me")

        prompt_id = int(lines[0].split(".", 1)[0])
        return json.dumps([{"id": prompt_id, "tag_id": 1, "score": 0.9}])


class DummyStorage:
    def begin_batch(self):
        pass

    def end_batch(self):
        pass


class AISelectionStrategyTest(unittest.TestCase):
    def test_service_runs_ai_strategy_and_persists_results(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_test_ai_config(config_root)
            _write_text(config_root / "custom" / "ai" / "unit.txt", "AI agents\nOpen source developer tools")

            storage = _build_storage(tmp)
            try:
                _seed_hotlist(storage)
                snapshot = _build_snapshot(storage)
                client = DeterministicAIClient()

                ai_strategy = AISelectionStrategy(
                    storage_manager=storage,
                    client=client,
                    filter_config={
                        "PROMPT_FILE": "prompt.txt",
                        "EXTRACT_PROMPT_FILE": "extract_prompt.txt",
                        "UPDATE_TAGS_PROMPT_FILE": "update_tags_prompt.txt",
                    },
                    config_root=config_root,
                    sleep_func=lambda _: None,
                )
                service = SelectionService(config_root=str(config_root), ai_strategy=ai_strategy)

                result = service.run(
                    snapshot,
                    SelectionOptions(
                        strategy="ai",
                        priority_sort_enabled=True,
                        ai=SelectionAIOptions(
                            interests_file="unit.txt",
                            batch_size=10,
                            batch_interval=0,
                            min_score=0.7,
                        ),
                    ),
                )

                self.assertEqual(result.strategy, "ai")
                self.assertEqual([group.label for group in result.groups], ["AI Agents", "Open Source"])
                self.assertEqual(
                    [item.title for item in result.selected_items],
                    ["OpenAI launches coding agent", "GitHub ships a new open source CLI"],
                )
                self.assertEqual(len(storage.get_active_ai_filter_tags(interests_file="unit.txt")), 2)
                self.assertEqual(len(storage.get_active_ai_filter_results(interests_file="unit.txt")), 2)
                self.assertEqual(storage.get_analyzed_news_ids("hotlist", interests_file="unit.txt"), {1, 2, 3})
                self.assertEqual(client.extract_calls, 1)
                self.assertEqual(client.classify_calls, 1)
            finally:
                storage.cleanup()

    def test_ai_strategy_incrementally_updates_tags_when_interest_changes(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_test_ai_config(config_root)
            interests_path = config_root / "custom" / "ai" / "unit.txt"
            _write_text(interests_path, "AI agents\nOpen source developer tools")

            storage = _build_storage(tmp)
            try:
                _seed_hotlist(storage)
                snapshot = _build_snapshot(storage)
                client = DeterministicAIClient()
                strategy = AISelectionStrategy(
                    storage_manager=storage,
                    client=client,
                    filter_config={
                        "PROMPT_FILE": "prompt.txt",
                        "EXTRACT_PROMPT_FILE": "extract_prompt.txt",
                        "UPDATE_TAGS_PROMPT_FILE": "update_tags_prompt.txt",
                        "RECLASSIFY_THRESHOLD": 0.6,
                    },
                    config_root=config_root,
                    sleep_func=lambda _: None,
                )

                options = SelectionOptions(
                    strategy="ai",
                    priority_sort_enabled=True,
                    ai=SelectionAIOptions(
                        interests_file="unit.txt",
                        batch_size=10,
                        batch_interval=0,
                        min_score=0.7,
                    ),
                )
                strategy.run(snapshot, options)
                initial_tags = storage.get_active_ai_filter_tags(interests_file="unit.txt")
                initial_ai_tag_id = next(tag["id"] for tag in initial_tags if tag["tag"] == "AI Agents")

                _write_text(interests_path, "AI agents\nStartup product launches")
                result = strategy.run(snapshot, options)

                active_tags = storage.get_active_ai_filter_tags(interests_file="unit.txt")
                self.assertEqual([tag["tag"] for tag in active_tags], ["AI Agents", "Startups"])
                self.assertEqual(active_tags[0]["id"], initial_ai_tag_id)
                self.assertEqual(result.diagnostics["tag_refresh_mode"], "incremental")
                self.assertEqual(client.update_calls, 1)
            finally:
                storage.cleanup()

    def test_ai_classify_batch_splits_failed_batch_until_single_item(self):
        with TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            _write_text(
                config_root / "ai_filter" / "prompt.txt",
                """
                [user]
                {news_list}
                """,
            )
            _write_text(config_root / "ai_filter" / "extract_prompt.txt", "[user]\nINTERESTS:\n{interests_content}")
            _write_text(config_root / "ai_filter" / "update_tags_prompt.txt", "[user]\nOLD:\n{old_tags_json}\nNEW:\n{interests_content}")

            client = SplitFallbackAIClient()
            strategy = AISelectionStrategy(
                storage_manager=DummyStorage(),
                client=client,
                filter_config={
                    "PROMPT_FILE": "prompt.txt",
                    "EXTRACT_PROMPT_FILE": "extract_prompt.txt",
                    "UPDATE_TAGS_PROMPT_FILE": "update_tags_prompt.txt",
                },
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
                [AIActiveTag(id=1, tag="AI", description="AI news", priority=1)],
                interests_content="AI",
            )

            self.assertEqual([result.news_item_id for result in results], ["1", "2", "3", "4"])
            self.assertEqual(client.calls[0], 4)
            self.assertIn(2, client.calls)
            self.assertIn(1, client.calls)


if __name__ == "__main__":
    unittest.main()
