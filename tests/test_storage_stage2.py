import unittest
from pathlib import Path
import shutil
import uuid

from newspulse.crawler import CrawlBatchResult, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import StorageManager, normalize_crawl_batch


class StorageStage2Test(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "storage-stage2"
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

    def test_normalize_crawl_batch_returns_native_stage2_contract(self):
        batch = normalize_crawl_batch(
            crawl_batch=CrawlBatchResult(
                sources=[
                    SourceFetchResult(
                        source_id="s1",
                        source_name="平台1",
                        resolved_source_id="s1",
                        items=[
                            SourceItem(title="Alpha", url="https://example.com/a"),
                            SourceItem(title="Alpha", url="https://example.com/a2"),
                            SourceItem(title="Beta", url="https://example.com/b"),
                        ],
                    )
                ],
                failures=[
                    SourceFetchFailure(
                        source_id="s2",
                        source_name="平台2",
                        resolved_source_id="s2",
                        exception_type="TimeoutError",
                        message="timeout",
                        attempts=3,
                        retryable=True,
                    )
                ],
            ),
            crawl_time="2026-04-18 10:00:00",
            crawl_date="2026-04-18",
        )

        self.assertEqual(batch.id_to_name["s1"], "平台1")
        self.assertEqual(batch.id_to_name["s2"], "平台2")
        self.assertEqual(batch.failed_ids, ["s2"])
        alpha = next(item for item in batch.items["s1"] if item.title == "Alpha")
        self.assertEqual(alpha.ranks, [1, 2])
        self.assertEqual(batch.failures[0].exception_type, "TimeoutError")
        self.assertEqual(batch.failures[0].message, "timeout")

    def test_storage_persists_structured_failure_details(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            first_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id="s1",
                            source_name="平台1",
                            resolved_source_id="s1",
                            items=[SourceItem(title="Alpha", url="https://example.com/a")],
                        )
                    ],
                    failures=[],
                ),
                crawl_time="2026-04-18 09:00:00",
                crawl_date="2026-04-18",
            )
            second_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id="s1",
                            source_name="平台1",
                            resolved_source_id="s1",
                            items=[SourceItem(title="Alpha", url="https://example.com/a")],
                        )
                    ],
                    failures=[
                        SourceFetchFailure(
                            source_id="s2",
                            source_name="平台2",
                            resolved_source_id="s2",
                            exception_type="ConnectionError",
                            message="boom",
                            attempts=2,
                            retryable=False,
                        )
                    ],
                ),
                crawl_time="2026-04-18 10:00:00",
                crawl_date="2026-04-18",
            )

            self.assertTrue(storage.save_normalized_crawl_batch(first_batch))
            self.assertTrue(storage.save_normalized_crawl_batch(second_batch))

            latest = storage.get_latest_crawl_data()
            all_data = storage.get_today_all_data()
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIsNotNone(latest)
        self.assertIsNotNone(all_data)
        assert latest is not None
        assert all_data is not None
        self.assertEqual(latest.failed_ids, ["s2"])
        self.assertEqual(latest.failures[0].source_name, "平台2")
        self.assertEqual(latest.failures[0].exception_type, "ConnectionError")
        self.assertEqual(latest.failures[0].message, "boom")
        self.assertEqual(latest.failures[0].attempts, 2)
        self.assertEqual(all_data.failures[0].source_id, "s2")
        self.assertEqual(all_data.items["s1"][0].ranks, [1])

    def test_latest_data_still_restores_failures_when_all_sources_fail(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            failed_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[],
                    failures=[
                        SourceFetchFailure(
                            source_id="s2",
                            source_name="平台2",
                            resolved_source_id="s2",
                            exception_type="TimeoutError",
                            message="down",
                            attempts=3,
                            retryable=True,
                        )
                    ],
                ),
                crawl_time="2026-04-18 11:00:00",
                crawl_date="2026-04-18",
            )
            self.assertTrue(storage.save_normalized_crawl_batch(failed_batch))
            latest = storage.get_latest_crawl_data()
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.items, {})
        self.assertEqual(latest.failed_ids, ["s2"])
        self.assertEqual(latest.failures[0].reason, "TimeoutError: down")


if __name__ == "__main__":
    unittest.main()
