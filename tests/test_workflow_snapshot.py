import unittest
from datetime import datetime
from pathlib import Path
import shutil
import uuid
from zoneinfo import ZoneInfo

from newspulse.crawler import CrawlBatchResult, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import StorageManager, convert_crawl_batch_to_news_data
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.snapshot.service import SnapshotService


TEST_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _today_str() -> str:
    return datetime.now(TEST_TIMEZONE).date().isoformat()


def _today_at(time_text: str) -> str:
    return f"{_today_str()} {time_text}"


def _save_crawl(storage: StorageManager, crawl_time: str, results: dict, failed_ids=None) -> None:
    sources = []
    for source_id, titles_data in results.items():
        items = []
        for title, title_data in titles_data.items():
            ranks = list(title_data.get("ranks", []))
            url = title_data.get("url", "")
            mobile_url = title_data.get("mobileUrl", "")
            summary = title_data.get("summary", "")
            metadata = dict(title_data.get("metadata", {}) or {})
            for index, rank in enumerate(ranks, start=1):
                position = rank if rank else index
                while len(items) < position - 1:
                    items.append(SourceItem(title=""))
                items.append(
                    SourceItem(
                        title=title,
                        url=url,
                        mobile_url=mobile_url,
                        summary=summary,
                        metadata=metadata,
                    )
                )
        sources.append(
            SourceFetchResult(
                source_id=source_id,
                source_name={"s1": "平台1", "s2": "平台2"}.get(source_id, source_id),
                resolved_source_id=source_id,
                items=items,
            )
        )

    failures = [
        SourceFetchFailure(
            source_id=failed_id,
            source_name={"s1": "平台1", "s2": "平台2", "s3": "平台3"}.get(failed_id, failed_id),
            resolved_source_id=failed_id,
            exception_type="RuntimeError",
            message="failed",
        )
        for failed_id in list(failed_ids or [])
    ]
    data = convert_crawl_batch_to_news_data(
        crawl_batch=CrawlBatchResult(sources=sources, failures=failures),
        crawl_time=crawl_time,
        crawl_date=_today_str(),
    )
    ok = storage.save_news_data(data)
    if not ok:
        raise AssertionError("failed to save crawl data")


class SnapshotServiceTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "workflow-snapshot"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _create_storage(self, tmp_path: Path) -> StorageManager:
        return StorageManager(
            backend_type="local",
            data_dir=str(tmp_path / "output"),
            enable_txt=False,
            enable_html=False,
        )

    def test_snapshot_service_builds_daily_current_and_incremental_views(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            _save_crawl(
                storage,
                _today_at("09:00:00"),
                {
                    "s1": {
                        "Alpha": {"ranks": [1], "url": "https://example.com/a", "mobileUrl": ""},
                        "Beta": {"ranks": [2], "url": "https://example.com/b", "mobileUrl": ""},
                    },
                    "s2": {
                        "Gamma": {"ranks": [1], "url": "https://example.com/g", "mobileUrl": ""},
                    },
                },
            )
            _save_crawl(
                storage,
                _today_at("10:00:00"),
                {
                    "s1": {
                        "Alpha": {"ranks": [2], "url": "https://example.com/a", "mobileUrl": ""},
                        "Charlie": {"ranks": [1], "url": "https://example.com/c", "mobileUrl": ""},
                    },
                    "s2": {
                        "Gamma": {"ranks": [2], "url": "https://example.com/g", "mobileUrl": ""},
                    },
                },
                failed_ids=["s3"],
            )

            service = SnapshotService(
                storage,
                platform_ids=["s1", "s2"],
                platform_names={"s1": "平台1", "s2": "平台2", "s3": "平台3"},
                standalone_platform_ids=["s2"],
                standalone_max_items=10,
            )

            daily = service.build(SnapshotOptions(mode="daily"))
            current = service.build(SnapshotOptions(mode="current"))
            incremental = service.build(SnapshotOptions(mode="incremental"))

            self.assertEqual({item.title for item in daily.items}, {"Alpha", "Beta", "Charlie", "Gamma"})
            self.assertEqual({item.title for item in daily.new_items}, {"Charlie"})
            self.assertEqual({item.title for item in current.items}, {"Alpha", "Charlie", "Gamma"})
            self.assertEqual({item.title for item in incremental.items}, {"Charlie"})
            self.assertEqual(current.failed_sources[0].source_name, "平台3")
            self.assertEqual(current.failed_sources[0].reason, "RuntimeError: failed")
            self.assertEqual(current.failed_sources[0].exception_type, "RuntimeError")
            self.assertEqual(current.standalone_sections[0].label, "平台2")
            self.assertEqual(current.standalone_sections[0].items[0].title, "Gamma")

            daily_alpha = next(item for item in daily.items if item.title == "Alpha")
            current_alpha = next(item for item in current.items if item.title == "Alpha")
            current_charlie = next(item for item in current.items if item.title == "Charlie")
            incremental_charlie = next(item for item in incremental.items if item.title == "Charlie")
            self.assertEqual(daily_alpha.ranks, [1, 2])
            self.assertEqual(current_alpha.ranks, [1, 2])
            self.assertEqual(current_alpha.count, 2)
            self.assertEqual(current_alpha.first_time, _today_at("09:00:00"))
            self.assertEqual(current_alpha.last_time, _today_at("10:00:00"))
            self.assertEqual(len(current_alpha.rank_timeline), 2)
            self.assertEqual(current_charlie.news_item_id, incremental_charlie.news_item_id)
            self.assertTrue(incremental_charlie.is_new)
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_incremental_snapshot_on_first_crawl_uses_latest_items(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            _save_crawl(
                storage,
                _today_at("09:00:00"),
                {
                    "s1": {
                        "Alpha": {"ranks": [1], "url": "https://example.com/a", "mobileUrl": ""},
                    },
                    "s2": {
                        "Gamma": {"ranks": [1], "url": "https://example.com/g", "mobileUrl": ""},
                    },
                },
            )

            service = SnapshotService(
                storage,
                platform_ids=["s1", "s2"],
                platform_names={"s1": "平台1", "s2": "平台2"},
                standalone_platform_ids=["s2"],
            )
            snapshot = service.build(SnapshotOptions(mode="incremental"))

            self.assertEqual({item.title for item in snapshot.items}, {"Alpha", "Gamma"})
            self.assertEqual({item.title for item in snapshot.new_items}, {"Alpha", "Gamma"})
            self.assertEqual(snapshot.summary["is_first_crawl"], True)
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_output_remains_usable_after_build(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            _save_crawl(
                storage,
                _today_at("09:00:00"),
                {
                    "s1": {
                        "Alpha": {"ranks": [1], "url": "https://example.com/a", "mobileUrl": ""},
                    },
                    "s2": {
                        "Gamma": {"ranks": [1], "url": "https://example.com/g", "mobileUrl": ""},
                    },
                },
                failed_ids=["s3"],
            )

            service = SnapshotService(
                storage,
                platform_ids=["s1", "s2"],
                platform_names={"s1": "platform-1", "s2": "platform-2", "s3": "platform-3"},
                standalone_platform_ids=["s2"],
            )
            snapshot = service.build(SnapshotOptions(mode="current"))
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

            def _boom(*args, **kwargs):
                raise AssertionError("snapshot should not need storage after build")

            storage.get_latest_crawl_data = _boom
            storage.get_today_all_data = _boom
            storage.news_repo.list_all_news_ids = _boom
            storage.is_first_crawl_today = _boom

            self.assertEqual(snapshot.summary["total_items"], 2)
            self.assertEqual({item.title for item in snapshot.items}, {"Alpha", "Gamma"})
            self.assertEqual(snapshot.failed_sources[0].source_id, "s3")
            self.assertEqual(snapshot.standalone_sections[0].items[0].title, "Gamma")

    def test_snapshot_service_returns_empty_snapshot_when_storage_is_empty(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            service = SnapshotService(
                storage,
                platform_ids=["s1", "s2"],
                platform_names={"s1": "platform-1", "s2": "platform-2"},
                standalone_platform_ids=["s2"],
            )
            snapshot = service.build(SnapshotOptions(mode="daily"))

            self.assertEqual(snapshot.generated_at, "")
            self.assertEqual(snapshot.items, [])
            self.assertEqual(snapshot.new_items, [])
            self.assertEqual(snapshot.failed_sources, [])
            self.assertEqual(snapshot.standalone_sections, [])
            self.assertEqual(snapshot.summary["total_items"], 0)
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_service_keeps_failure_details_when_latest_crawl_has_no_items(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            failed_data = convert_crawl_batch_to_news_data(
                crawl_batch=CrawlBatchResult(
                    sources=[],
                    failures=[
                        SourceFetchFailure(
                            source_id="s3",
                            source_name="platform-3",
                            resolved_source_id="s3",
                            exception_type="TimeoutError",
                            message="down",
                            attempts=3,
                        )
                    ],
                ),
                crawl_time=_today_at("11:00:00"),
                crawl_date=_today_str(),
            )
            self.assertTrue(storage.save_news_data(failed_data))

            service = SnapshotService(
                storage,
                platform_ids=["s1", "s2", "s3"],
                platform_names={"s1": "platform-1", "s2": "platform-2", "s3": "platform-3"},
                standalone_platform_ids=["s2"],
            )

            current = service.build(SnapshotOptions(mode="current"))
            incremental = service.build(SnapshotOptions(mode="incremental"))

            self.assertEqual(current.items, [])
            self.assertEqual(incremental.items, [])
            self.assertEqual(current.failed_sources[0].source_id, "s3")
            self.assertEqual(current.failed_sources[0].reason, "TimeoutError: down")
            self.assertEqual(current.summary["total_failed_sources"], 1)
            self.assertEqual(incremental.summary["total_new_items"], 0)
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_service_ignores_unavailable_standalone_platforms(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            _save_crawl(
                storage,
                _today_at("09:00:00"),
                {
                    "s1": {
                        "Alpha": {"ranks": [1], "url": "https://example.com/a", "mobileUrl": ""},
                    },
                    "s2": {
                        "Gamma": {"ranks": [1], "url": "https://example.com/g", "mobileUrl": ""},
                    },
                },
            )

            service = SnapshotService(
                storage,
                platform_ids=["s1"],
                platform_names={"s1": "platform-1", "s2": "platform-2"},
                standalone_platform_ids=["s2", "missing"],
            )
            snapshot = service.build(SnapshotOptions(mode="current"))

            self.assertEqual([item.source_id for item in snapshot.items], ["s1"])
            self.assertEqual(snapshot.standalone_sections, [])
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_snapshot_service_keeps_structured_context_on_hotlist_items(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            _save_crawl(
                storage,
                _today_at("09:00:00"),
                {
                    "s1": {
                        "openai/openai-agents-python": {
                            "ranks": [1],
                            "url": "https://github.com/openai/openai-agents-python",
                            "summary": "Official OpenAI Agents SDK for Python",
                            "metadata": {
                                "source_context_version": 1,
                                "source_kind": "github_repository",
                                "github": {
                                    "full_name": "openai/openai-agents-python",
                                    "language": "Python",
                                    "topics": ["openai", "agent", "sdk"],
                                },
                            },
                        }
                    }
                },
            )

            service = SnapshotService(
                storage,
                platform_ids=["s1"],
                platform_names={"s1": "GitHub Trending"},
            )
            snapshot = service.build(SnapshotOptions(mode="current"))
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(len(snapshot.items), 1)
        self.assertEqual(snapshot.items[0].summary, "Official OpenAI Agents SDK for Python")
        self.assertEqual(snapshot.items[0].metadata["source_kind"], "github_repository")
        self.assertEqual(snapshot.items[0].metadata["github"]["topics"], ["openai", "agent", "sdk"])


if __name__ == "__main__":
    unittest.main()
