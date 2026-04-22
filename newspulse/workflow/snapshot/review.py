# coding=utf-8
"""Stage-3 review exporter for snapshot construction."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from newspulse.core import load_config
from newspulse.crawler.fetcher import DataFetcher
from newspulse.crawler.models import CrawlBatchResult, CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.storage import NewsData, NormalizedCrawlBatch, StorageManager, normalize_crawl_batch
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.shared.review_helpers import (
    ReviewOutboxWriter as _ReviewOutboxWriter,
    build_source_specs as _build_source_specs,
)
from newspulse.workflow.snapshot import SnapshotService

SNAPSHOT_MODES = ("daily", "current", "incremental")


def _snapshot_mode_summary(snapshot) -> dict[str, object]:
    return {
        "generated_at": snapshot.generated_at,
        "item_count": len(snapshot.items),
        "new_item_count": len(snapshot.new_items),
        "failed_source_count": len(snapshot.failed_sources),
        "standalone_section_count": len(snapshot.standalone_sections),
        "summary": dict(snapshot.summary),
    }


def _build_snapshot_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    request_interval_ms: int,
    source_specs: Sequence[CrawlSourceSpec],
    crawl_batch: CrawlBatchResult,
    normalized_batch: NormalizedCrawlBatch,
    latest_data: NewsData | None,
    snapshots: dict[str, object],
) -> str:
    lines: list[str] = []
    lines.append("# Stage 3 Snapshot Review")
    lines.append("")
    lines.append(f"- generated_at: {generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append(f"- config_path: `{config_path}`")
    lines.append(f"- storage_data_dir: `{storage_data_dir}`")
    lines.append(f"- request_interval_ms: {request_interval_ms}")
    lines.append(f"- requested_source_count: {len(source_specs)}")
    lines.append(f"- crawl_success_count: {len(crawl_batch.sources)}")
    lines.append(f"- crawl_failure_count: {len(crawl_batch.failures)}")
    lines.append(
        f"- normalized_total_items: {sum(len(source.items) for source in normalized_batch.sources)}"
    )
    lines.append(
        f"- latest_readback_total_items: {latest_data.get_total_count() if latest_data else 0}"
    )
    lines.append("")
    lines.append("## Requested Sources")
    lines.append("")
    for spec in source_specs:
        lines.append(f"- `{spec.source_id}` / {spec.source_name}")

    lines.append("")
    lines.append("## Snapshot Modes")
    lines.append("")
    for mode in SNAPSHOT_MODES:
        snapshot = snapshots[mode]
        lines.append(f"### {mode}")
        lines.append("")
        lines.append(f"- generated_at: `{snapshot.generated_at}`")
        lines.append(f"- item_count: {len(snapshot.items)}")
        lines.append(f"- new_item_count: {len(snapshot.new_items)}")
        lines.append(f"- failed_source_count: {len(snapshot.failed_sources)}")
        lines.append(f"- standalone_section_count: {len(snapshot.standalone_sections)}")
        lines.append("")
        for index, item in enumerate(snapshot.items[:20], start=1):
            lines.append(
                f"{index}. [{item.source_id}] [{item.current_rank}] {item.title}"
            )
        if len(snapshot.items) > 20:
            lines.append(f"... ({len(snapshot.items) - 20} more items)")
        lines.append("")

    return "\n".join(lines)


def export_snapshot_outbox(
    *,
    outbox_dir: str | Path,
    generated_at: datetime,
    config_path: str | Path,
    storage_data_dir: str | Path,
    request_interval_ms: int,
    source_specs: Sequence[CrawlSourceSpec],
    crawl_batch: CrawlBatchResult,
    normalized_batch: NormalizedCrawlBatch,
    latest_data: NewsData | None,
    snapshots: dict[str, object],
    run_log: str,
) -> dict[str, object]:
    outbox = _ReviewOutboxWriter(outbox_dir)
    config_path_obj = Path(config_path)
    storage_path = Path(storage_data_dir)

    summary = {
        "generated_at": generated_at.isoformat(),
        "config_path": str(config_path_obj),
        "storage_data_dir": str(storage_path),
        "request_interval_ms": request_interval_ms,
        "requested_sources": [asdict(spec) for spec in source_specs],
        "crawl": {
            "success_count": len(crawl_batch.sources),
            "failure_count": len(crawl_batch.failures),
            "successful_source_ids": crawl_batch.successful_source_ids,
            "failed_source_ids": crawl_batch.failed_source_ids,
        },
        "normalized": {
            "source_count": len(normalized_batch.sources),
            "failure_count": len(normalized_batch.failures),
            "total_items": sum(len(source.items) for source in normalized_batch.sources),
        },
        "latest_readback": {
            "exists": latest_data is not None,
            "crawl_time": latest_data.crawl_time if latest_data else "",
            "source_count": len(latest_data.items) if latest_data else 0,
            "total_items": latest_data.get_total_count() if latest_data else 0,
            "failure_count": len(latest_data.failures) if latest_data else 0,
        },
        "snapshots": {
            mode: _snapshot_mode_summary(snapshot)
            for mode, snapshot in snapshots.items()
        },
    }

    outbox.write_stage_json(
        "stage3_crawl_batch.json",
        summary=summary,
        batch=asdict(crawl_batch),
    )
    outbox.write_stage_json(
        "stage3_normalized_batch.json",
        summary=summary,
        batch=normalized_batch.to_dict(),
    )
    outbox.write_stage_json(
        "stage3_latest_news_data.json",
        summary=summary,
        latest=latest_data.to_dict() if latest_data else None,
    )
    for mode, snapshot in snapshots.items():
        outbox.write_stage_json(
            f"stage3_snapshot_{mode}.json",
            summary=summary,
            snapshot=asdict(snapshot),
        )

    outbox.write_markdown(
        "stage3_snapshot_review.md",
        _build_snapshot_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            request_interval_ms=request_interval_ms,
            source_specs=source_specs,
            crawl_batch=crawl_batch,
            normalized_batch=normalized_batch,
            latest_data=latest_data,
            snapshots=snapshots,
        ),
    )
    outbox.write_log("stage3_snapshot_run.log", run_log)
    return summary


def run_snapshot_review(
    *,
    config_path: str | Path = "config/config.yaml",
    outbox_dir: str | Path = "outbox",
    storage_data_dir: str | Path | None = None,
) -> dict[str, object]:
    log_buffer = StringIO()
    resolved_config_path = Path(config_path).resolve()
    outbox_path = Path(outbox_dir)
    resolved_storage_dir = Path(storage_data_dir) if storage_data_dir else outbox_path / "stage3_storage"

    latest_data: NewsData | None = None
    snapshots: dict[str, object] = {}

    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        config = load_config(str(resolved_config_path))
        timezone_name = config.get("TIMEZONE", DEFAULT_TIMEZONE)
        source_specs = _build_source_specs(config["PLATFORMS"])
        request_interval_ms = int(config["REQUEST_INTERVAL"])
        proxy_url = config["DEFAULT_PROXY"] if config.get("USE_PROXY") else None

        crawl_batch = DataFetcher(proxy_url=proxy_url).crawl(
            source_specs,
            request_interval=request_interval_ms,
        )
        generated_at = datetime.now(ZoneInfo(timezone_name))
        crawl_time = generated_at.strftime("%Y-%m-%d %H:%M:%S")
        crawl_date = generated_at.date().isoformat()
        normalized_batch = normalize_crawl_batch(
            crawl_batch=crawl_batch,
            crawl_time=crawl_time,
            crawl_date=crawl_date,
        )

        storage = StorageManager(
            backend_type="local",
            data_dir=str(resolved_storage_dir),
            enable_txt=False,
            enable_html=False,
            timezone=timezone_name,
        )
        try:
            save_success = storage.save_normalized_crawl_batch(normalized_batch)
            if not save_success:
                raise RuntimeError("failed to save normalized crawl batch")
            latest_data = storage.get_latest_crawl_data(crawl_date)

            standalone_config = config.get("DISPLAY", {}).get("STANDALONE", {})
            snapshot_service = SnapshotService(
                storage,
                platform_ids=[
                    str(platform["id"])
                    for platform in config["PLATFORMS"]
                    if platform.get("id")
                ],
                platform_names={
                    str(platform["id"]): resolve_source_display_name(
                        str(platform["id"]),
                        str(platform.get("name", "") or ""),
                    )
                    for platform in config["PLATFORMS"]
                    if platform.get("id")
                },
                standalone_platform_ids=list(standalone_config.get("PLATFORMS", [])),
                standalone_max_items=int(standalone_config.get("MAX_ITEMS", 20) or 20),
            )
            snapshots = {
                mode: snapshot_service.build(SnapshotOptions(mode=mode))
                for mode in SNAPSHOT_MODES
            }
        finally:
            storage.cleanup()

    return export_snapshot_outbox(
        outbox_dir=outbox_dir,
        generated_at=generated_at,
        config_path=resolved_config_path,
        storage_data_dir=resolved_storage_dir,
        request_interval_ms=request_interval_ms,
        source_specs=source_specs,
        crawl_batch=crawl_batch,
        normalized_batch=normalized_batch,
        latest_data=latest_data,
        snapshots=snapshots,
        run_log=log_buffer.getvalue(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run crawl -> normalize -> store -> snapshot validation and export stage-3 artifacts.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--outbox", default="outbox")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_snapshot_review(
        config_path=args.config,
        outbox_dir=args.outbox,
        storage_data_dir=args.data_dir,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
