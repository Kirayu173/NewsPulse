import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from newspulse.crawler.models import CrawlBatchResult, CrawlSourceSpec, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.review import export_crawl_outbox
from newspulse.crawler.sources.base import SourceItem


class CrawlReviewExportTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "crawler-review"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_export_crawl_outbox_writes_readable_utf8_review_artifacts(self):
        batch = CrawlBatchResult(
            sources=[
                SourceFetchResult(
                    source_id="thepaper",
                    source_name="\u6f8e\u6e43\u65b0\u95fb",
                    resolved_source_id="thepaper",
                    items=[
                        SourceItem(
                            title="\u73b0\u573a\u753b\u9762\u4e28\u89e3\u653e\u519b\u51cc\u6668\u56db\u70b9\u7ba1\u63a7\u65e5\u8230\u8fc7\u822a\u53f0\u6e7e\u6d77\u5ce1",
                            url="https://example.com/a",
                            mobile_url="https://m.example.com/a",
                        )
                    ],
                    attempts=1,
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
                )
            ],
        )
        source_specs = [
            CrawlSourceSpec(source_id="thepaper", source_name="\u6f8e\u6e43\u65b0\u95fb"),
            CrawlSourceSpec(source_id="github-trending-today", source_name="GitHub Trending"),
        ]

        tmpdir = self._create_workspace_tmpdir()
        try:
            summary = export_crawl_outbox(
                outbox_dir=tmpdir,
                generated_at=datetime(2026, 4, 18, 21, 30, tzinfo=timezone.utc),
                request_interval_ms=2000,
                source_specs=source_specs,
                crawl_batch=batch,
                crawl_log="crawl ok",
            )

            review_text = (Path(tmpdir) / "crawl_review.md").read_text(encoding="utf-8-sig")
            batch_payload = json.loads((Path(tmpdir) / "crawl_batch.json").read_text(encoding="utf-8-sig"))
            log_text = (Path(tmpdir) / "crawl_run.log").read_text(encoding="utf-8-sig")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(summary["success_count"], 1)
        self.assertIn("\u751f\u6210\u65f6\u95f4", review_text)
        self.assertIn("\u6f8e\u6e43\u65b0\u95fb", review_text)
        self.assertIn(
            "\u73b0\u573a\u753b\u9762\u4e28\u89e3\u653e\u519b\u51cc\u6668\u56db\u70b9\u7ba1\u63a7\u65e5\u8230\u8fc7\u822a\u53f0\u6e7e\u6d77\u5ce1",
            review_text,
        )
        self.assertEqual(
            batch_payload["summary"]["requested_sources"][0]["source_name"],
            "\u6f8e\u6e43\u65b0\u95fb",
        )
        self.assertEqual(
            batch_payload["batch"]["sources"][0]["items"][0]["title"],
            "\u73b0\u573a\u753b\u9762\u4e28\u89e3\u653e\u519b\u51cc\u6668\u56db\u70b9\u7ba1\u63a7\u65e5\u8230\u8fc7\u822a\u53f0\u6e7e\u6d77\u5ce1",
        )
        self.assertEqual(log_text, "crawl ok")


if __name__ == "__main__":
    unittest.main()
