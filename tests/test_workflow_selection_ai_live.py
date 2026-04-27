import os
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from newspulse.core.loader import load_config
from newspulse.storage.base import NewsData, NewsItem
from newspulse.storage.local import LocalStorageBackend
from newspulse.workflow.selection.service import SelectionService
from newspulse.workflow.shared.options import SelectionAIOptions, SelectionOptions, SnapshotOptions
from newspulse.workflow.snapshot.service import SnapshotService
from tests.helpers.io import write_text
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory

TEST_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _today_str() -> str:
    return datetime.now(TEST_TIMEZONE).date().isoformat()


def _today_at(time_text: str) -> str:
    return f"{_today_str()} {time_text}"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class LiveAISelectionStrategyTest(unittest.TestCase):
    def test_ai_selection_stage_runs_with_real_model(self):
        project_root = Path(__file__).resolve().parents[1]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            self.skipTest("live AI tests disabled")
        config = load_config(str(project_root / "config" / "config.yaml"))

        with TemporaryDirectory() as tmp:
            storage = LocalStorageBackend(
                data_dir=str(Path(tmp) / "output"),
                enable_txt=False,
                enable_html=False,
                timezone="Asia/Shanghai",
            )
            try:
                storage.save_news_data(
                    NewsData(
                        date=_today_str(),
                        crawl_time=_today_at("10:00:00"),
                        items={
                            "hackernews": [
                                NewsItem(
                                    title="OpenAI launches a new coding agent",
                                    source_id="hackernews",
                                    source_name="Hacker News",
                                    rank=1,
                                    url="https://example.com/openai-live",
                                    mobile_url="https://m.example.com/openai-live",
                                    crawl_time=_today_at("10:00:00"),
                                    ranks=[1],
                                    first_time=_today_at("10:00:00"),
                                    last_time=_today_at("10:00:00"),
                                    count=1,
                                ),
                                NewsItem(
                                    title="GitHub releases a new open source developer tool",
                                    source_id="hackernews",
                                    source_name="Hacker News",
                                    rank=2,
                                    url="https://example.com/github-live",
                                    mobile_url="https://m.example.com/github-live",
                                    crawl_time=_today_at("10:00:00"),
                                    ranks=[2],
                                    first_time=_today_at("10:00:00"),
                                    last_time=_today_at("10:00:00"),
                                    count=1,
                                ),
                                NewsItem(
                                    title="NBA finals schedule announced",
                                    source_id="hackernews",
                                    source_name="Hacker News",
                                    rank=3,
                                    url="https://example.com/nba-live",
                                    mobile_url="https://m.example.com/nba-live",
                                    crawl_time=_today_at("10:00:00"),
                                    ranks=[3],
                                    first_time=_today_at("10:00:00"),
                                    last_time=_today_at("10:00:00"),
                                    count=1,
                                ),
                            ]
                        },
                        id_to_name={"hackernews": "Hacker News"},
                        failed_ids=[],
                    )
                )

                snapshot = SnapshotService(
                    storage,
                    platform_ids=["hackernews"],
                    platform_names={"hackernews": "Hacker News"},
                ).build(SnapshotOptions(mode="current"))

                temp_config_root = Path(tmp) / "config"
                write_text(
                    temp_config_root / "custom" / "ai" / "live.txt",
                    "AI agents and large models\nOpen source developer tools\nstartup product launches",
                )

                selection_service = SelectionService(
                    config_root=str(temp_config_root),
                    storage_manager=storage,
                    ai_runtime_config=config["AI_FILTER_MODEL"],
                    ai_filter_config=config["AI_FILTER"],
                    debug=bool(config.get("DEBUG", False)),
                )
                result = selection_service.run(
                    snapshot,
                    SelectionOptions(
                        strategy="ai",
                        priority_sort_enabled=True,
                        ai=SelectionAIOptions(
                            interests_file="live.txt",
                            batch_size=3,
                            batch_interval=0,
                            min_score=0.5,
                        ),
                    ),
                )

                self.assertEqual(result.strategy, "ai")
                self.assertGreaterEqual(result.total_selected, 1)
                self.assertGreaterEqual(result.diagnostics.get("active_tag_count", 0), 1)
                selected_titles = {item.title for item in result.selected_items}
                self.assertTrue(
                    {
                        "OpenAI launches a new coding agent",
                        "GitHub releases a new open source developer tool",
                    }
                    & selected_titles
                )
            finally:
                storage.cleanup()


if __name__ == "__main__":
    unittest.main()
