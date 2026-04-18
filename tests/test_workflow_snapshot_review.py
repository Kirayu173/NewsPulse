import json
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from newspulse.crawler import CrawlBatchResult, CrawlSourceSpec, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import normalize_crawl_batch
from newspulse.workflow.shared.contracts import HotlistItem, HotlistSnapshot
from newspulse.workflow.snapshot.review import export_snapshot_outbox


class SnapshotReviewExportTest(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path(".tmp-test") / "workflow-snapshot-review"
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_export_snapshot_outbox_writes_mode_artifacts(self):
        crawl_batch = CrawlBatchResult(
            sources=[
                SourceFetchResult(
                    source_id="thepaper",
                    source_name="\u6f8e\u6e43\u65b0\u95fb",
                    resolved_source_id="thepaper",
                    items=[
                        SourceItem(
                            title="\u73b0\u573a\u753b\u9762",
                            url="https://example.com/a",
                        ),
                        SourceItem(
                            title="OpenAI ships new tools",
                            url="https://example.com/b",
                        ),
                    ],
                    attempts=1,
                    metadata={"category": "mainland"},
                )
            ]
        )
        normalized_batch = normalize_crawl_batch(
            crawl_batch=crawl_batch,
            crawl_time="2026-04-18 23:40:00",
            crawl_date="2026-04-18",
        )
        latest_data = normalized_batch.to_news_data()
        source_specs = [
            CrawlSourceSpec(source_id="thepaper", source_name="\u6f8e\u6e43\u65b0\u95fb"),
        ]
        snapshots = {
            mode: HotlistSnapshot(
                mode=mode,
                generated_at="2026-04-18 23:40:00",
                items=[
                    HotlistItem(
                        news_item_id="1",
                        source_id="thepaper",
                        source_name="\u6f8e\u6e43\u65b0\u95fb",
                        title="\u73b0\u573a\u753b\u9762",
                        current_rank=1,
                        ranks=[1],
                    )
                ],
                new_items=[] if mode == "daily" else [],
                summary={"mode": mode, "total_items": 1},
            )
            for mode in ("daily", "current", "incremental")
        }

        tmpdir = self._create_workspace_tmpdir()
        try:
            summary = export_snapshot_outbox(
                outbox_dir=tmpdir,
                generated_at=datetime(2026, 4, 18, 23, 41, tzinfo=timezone.utc),
                config_path="config/config.yaml",
                storage_data_dir=Path(tmpdir) / "stage3_storage",
                request_interval_ms=2000,
                source_specs=source_specs,
                crawl_batch=crawl_batch,
                normalized_batch=normalized_batch,
                latest_data=latest_data,
                snapshots=snapshots,
                run_log="stage3 ok",
            )

            review_text = (Path(tmpdir) / "stage3_snapshot_review.md").read_text(
                encoding="utf-8-sig"
            )
            current_payload = json.loads(
                (Path(tmpdir) / "stage3_snapshot_current.json").read_text(
                    encoding="utf-8-sig"
                )
            )
            run_log = (Path(tmpdir) / "stage3_snapshot_run.log").read_text(
                encoding="utf-8-sig"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(summary["snapshots"]["current"]["item_count"], 1)
        self.assertIn("Stage 3 Snapshot Review", review_text)
        self.assertIn("\u6f8e\u6e43\u65b0\u95fb", review_text)
        self.assertEqual(
            current_payload["snapshot"]["items"][0]["title"],
            "\u73b0\u573a\u753b\u9762",
        )
        self.assertEqual(run_log, "stage3 ok")


if __name__ == "__main__":
    unittest.main()
