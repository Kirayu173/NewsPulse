import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from newspulse.crawler import CrawlBatchResult, CrawlSourceSpec, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import normalize_crawl_batch
from newspulse.storage.review import export_stage2_outbox


class StorageReviewExportTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "storage-review"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_export_stage2_outbox_writes_utf8_review_artifacts(self):
        crawl_batch = CrawlBatchResult(
            sources=[
                SourceFetchResult(
                    source_id="thepaper",
                    source_name="\u6f8e\u6e43\u65b0\u95fb",
                    resolved_source_id="thepaper",
                    items=[
                        SourceItem(
                            title="\u4e2d\u4e1c\u5c40\u52bf\u6301\u7eed\u5347\u7ea7",
                            url="https://example.com/a",
                        ),
                        SourceItem(
                            title="\u4e2d\u4e1c\u5c40\u52bf\u6301\u7eed\u5347\u7ea7",
                            url="https://example.com/a2",
                        ),
                        SourceItem(
                            title="OpenAI ships new tools",
                            url="https://example.com/b",
                        ),
                    ],
                    attempts=2,
                    metadata={"category": "mainland"},
                )
            ],
            failures=[
                SourceFetchFailure(
                    source_id="github-trending-today",
                    source_name="GitHub Trending",
                    resolved_source_id="github-trending-today",
                    exception_type="ConnectionError",
                    message="timed out",
                    attempts=3,
                    retryable=True,
                    metadata={"category": "tech"},
                )
            ],
        )
        normalized_batch = normalize_crawl_batch(
            crawl_batch=crawl_batch,
            crawl_time="2026-04-18 22:30:00",
            crawl_date="2026-04-18",
        )
        latest_data = normalized_batch.to_news_data()
        source_specs = [
            CrawlSourceSpec(source_id="thepaper", source_name="\u6f8e\u6e43\u65b0\u95fb"),
            CrawlSourceSpec(source_id="github-trending-today", source_name="GitHub Trending"),
        ]

        tmpdir = self._create_workspace_tmpdir()
        try:
            summary = export_stage2_outbox(
                outbox_dir=tmpdir,
                generated_at=datetime(2026, 4, 18, 22, 31, tzinfo=timezone.utc),
                config_path="config/config.yaml",
                storage_data_dir=Path(tmpdir) / "stage2_storage",
                request_interval_ms=2000,
                source_specs=source_specs,
                crawl_batch=crawl_batch,
                normalized_batch=normalized_batch,
                latest_data=latest_data,
                run_log="stage2 ok",
            )

            review_text = (Path(tmpdir) / "stage2_review.md").read_text(encoding="utf-8-sig")
            normalized_payload = json.loads(
                (Path(tmpdir) / "stage2_normalized_batch.json").read_text(encoding="utf-8-sig")
            )
            latest_payload = json.loads(
                (Path(tmpdir) / "stage2_latest_news_data.json").read_text(encoding="utf-8-sig")
            )
            log_text = (Path(tmpdir) / "stage2_run.log").read_text(encoding="utf-8-sig")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(summary["crawl"]["success_count"], 1)
        self.assertEqual(summary["normalized"]["total_items"], 2)
        self.assertIn("Stage 2 Review", review_text)
        self.assertIn("\u6f8e\u6e43\u65b0\u95fb", review_text)
        self.assertIn("\u4e2d\u4e1c\u5c40\u52bf\u6301\u7eed\u5347\u7ea7", review_text)
        self.assertEqual(
            normalized_payload["batch"]["sources"][0]["items"][0]["title"],
            "\u4e2d\u4e1c\u5c40\u52bf\u6301\u7eed\u5347\u7ea7",
        )
        self.assertEqual(
            latest_payload["latest"]["failures"][0]["exception_type"],
            "ConnectionError",
        )
        self.assertEqual(log_text, "stage2 ok")


if __name__ == "__main__":
    unittest.main()
