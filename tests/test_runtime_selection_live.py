import os
import unittest
from pathlib import Path

from newspulse.core.loader import load_config
from newspulse.runtime import RuntimeProviders, build_runtime, run_selection_stage
from newspulse.storage import get_storage_manager
from newspulse.storage.base import NewsData, NewsItem
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory


def _today_at(runtime, time_text: str) -> str:
    return f"{runtime.settings.format_date()} {time_text}"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LiveRuntimeSelectionStageTest(unittest.TestCase):
    def test_context_run_selection_stage_uses_real_model(self):
        project_root = Path(__file__).resolve().parents[1]
        _load_dotenv(project_root / ".env")
        if os.environ.get("NEWSPULSE_RUN_LIVE_AI_TESTS") != "1":
            self.skipTest("live AI tests disabled")

        base_config = load_config(str(project_root / "config" / "config.yaml"))

        with TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            config_root = tmp_root / "config"
            output_dir = tmp_root / "output"
            (config_root / "custom" / "ai").mkdir(parents=True, exist_ok=True)
            (config_root / "custom" / "ai" / "live.txt").write_text(
                "AI agents and large models\nopen source developer tools\nstartup product launches",
                encoding="utf-8",
            )

            config = dict(base_config)
            config["STORAGE"] = {
                "BACKEND": "local",
                "FORMATS": {"TXT": False, "HTML": False},
                "LOCAL": {"DATA_DIR": str(output_dir), "RETENTION_DAYS": 0},
            }
            config["FILTER"] = {"METHOD": "ai", "PRIORITY_SORT_ENABLED": True}
            config["_PATHS"] = {
                **dict(base_config.get("_PATHS", {})),
                "CONFIG_ROOT": str(config_root),
            }

            storage = get_storage_manager(
                backend_type="local",
                data_dir=str(output_dir),
                enable_txt=False,
                enable_html=False,
                timezone=str(base_config.get("TIMEZONE", "Asia/Shanghai")),
            )
            runtime = build_runtime(
                config,
                providers=RuntimeProviders(storage_factory=lambda settings: storage),
            )
            try:
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
                                    url="https://example.com/openai-live",
                                    mobile_url="https://m.example.com/openai-live",
                                    crawl_time=_today_at(runtime, "10:00:00"),
                                    ranks=[1],
                                    first_time=_today_at(runtime, "10:00:00"),
                                    last_time=_today_at(runtime, "10:00:00"),
                                    count=1,
                                ),
                                NewsItem(
                                    title="GitHub releases a new open source developer tool",
                                    source_id="hackernews",
                                    source_name="Hacker News",
                                    rank=2,
                                    url="https://example.com/github-live",
                                    mobile_url="https://m.example.com/github-live",
                                    crawl_time=_today_at(runtime, "10:00:00"),
                                    ranks=[2],
                                    first_time=_today_at(runtime, "10:00:00"),
                                    last_time=_today_at(runtime, "10:00:00"),
                                    count=1,
                                ),
                                NewsItem(
                                    title="NBA finals schedule announced",
                                    source_id="hackernews",
                                    source_name="Hacker News",
                                    rank=3,
                                    url="https://example.com/nba-live",
                                    mobile_url="https://m.example.com/nba-live",
                                    crawl_time=_today_at(runtime, "10:00:00"),
                                    ranks=[3],
                                    first_time=_today_at(runtime, "10:00:00"),
                                    last_time=_today_at(runtime, "10:00:00"),
                                    count=1,
                                ),
                            ]
                        },
                        id_to_name={"hackernews": "Hacker News"},
                        failed_ids=[],
                    )
                )

                _, result = run_selection_stage(
                    runtime.settings,
                    runtime.container,
                    runtime.selection_builder,
                    mode="current",
                    strategy="ai",
                    interests_file="live.txt",
                )

                self.assertEqual(result.diagnostics["requested_strategy"], "ai")
                self.assertGreaterEqual(result.total_selected, 1)
                selected_titles = {item.title for item in result.selected_items}
                self.assertTrue(
                    {
                        "OpenAI launches a new coding agent",
                        "GitHub releases a new open source developer tool",
                    }
                    & selected_titles
                )
            finally:
                runtime.cleanup()


if __name__ == "__main__":
    unittest.main()
