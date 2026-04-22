# coding=utf-8
"""Stage-2 review exporter for crawl normalization and persistence."""

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
from newspulse.storage import NewsData, NormalizedCrawlBatch, StorageManager, normalize_crawl_batch
from newspulse.utils.time import DEFAULT_TIMEZONE
from newspulse.workflow.shared.review_helpers import (
    build_source_specs as _build_source_specs,
    write_review_text as _write_review_text,
)

def _build_stage2_review_markdown(
    *,
    generated_at: datetime,
    config_path: Path,
    storage_data_dir: Path,
    request_interval_ms: int,
    source_specs: Sequence[CrawlSourceSpec],
    crawl_batch: CrawlBatchResult,
    normalized_batch: NormalizedCrawlBatch,
    latest_data: NewsData | None,
) -> str:
    latest_total_items = latest_data.get_total_count() if latest_data else 0
    latest_failures = latest_data.failures if latest_data else []

    lines: list[str] = []
    lines.append("# Stage 2 Review")
    lines.append("")
    lines.append(
        f"- \u751f\u6210\u65f6\u95f4: {generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}"
    )
    lines.append(f"- \u914d\u7f6e\u6587\u4ef6: `{config_path}`")
    lines.append(f"- Stage 2 \u6570\u636e\u76ee\u5f55: `{storage_data_dir}`")
    lines.append(f"- \u8bf7\u6c42\u95f4\u9694: {request_interval_ms} ms")
    lines.append(f"- \u8bf7\u6c42\u6e90\u6570: {len(source_specs)}")
    lines.append(f"- Crawl \u6210\u529f: {len(crawl_batch.sources)}")
    lines.append(f"- Crawl \u5931\u8d25: {len(crawl_batch.failures)}")
    lines.append(f"- \u5f52\u4e00\u5316\u6210\u529f\u6e90: {len(normalized_batch.sources)}")
    lines.append(
        f"- \u5f52\u4e00\u5316\u603b\u6761\u76ee: {sum(len(source.items) for source in normalized_batch.sources)}"
    )
    lines.append(
        f"- \u5b58\u50a8\u8bfb\u56de latest \u6761\u76ee: {latest_total_items}"
    )
    lines.append(f"- \u5b58\u50a8\u8bfb\u56de latest \u5931\u8d25: {len(latest_failures)}")
    lines.append("")
    lines.append("## Requested Sources")
    lines.append("")
    for spec in source_specs:
        lines.append(f"- `{spec.source_id}` / {spec.source_name}")

    lines.append("")
    lines.append("## Normalized Sources")
    lines.append("")
    if normalized_batch.sources:
        for source in normalized_batch.sources:
            lines.append(f"### {source.source_name} (`{source.source_id}`)")
            lines.append("")
            lines.append(f"- \u5f52\u4e00\u5316\u6761\u6570: {len(source.items)}")
            if source.metadata:
                category = source.metadata.get("category", "")
                if category:
                    lines.append(f"- category: `{category}`")
            lines.append("")
            for index, item in enumerate(source.items, start=1):
                lines.append(f"{index}. {item.title}")
                if item.url:
                    lines.append(f"   - URL: {item.url}")
                if item.mobile_url and item.mobile_url != item.url:
                    lines.append(f"   - Mobile: {item.mobile_url}")
            lines.append("")
    else:
        lines.append("- \u65e0\u6210\u529f\u6e90")
        lines.append("")

    lines.append("## Structured Failures")
    lines.append("")
    if normalized_batch.failures:
        for failure in normalized_batch.failures:
            lines.append(f"- `{failure.source_id}` / {failure.source_name}")
            lines.append(f"  - resolved_source_id: `{failure.resolved_source_id}`")
            lines.append(f"  - exception: `{failure.exception_type}`")
            lines.append(f"  - message: {failure.message}")
            lines.append(f"  - attempts: {failure.attempts}")
            lines.append(f"  - retryable: `{failure.retryable}`")
    else:
        lines.append("- \u65e0\u5931\u8d25\u6e90")
    lines.append("")

    lines.append("## Storage Latest Readback")
    lines.append("")
    if latest_data:
        lines.append(f"- crawl_time: `{latest_data.crawl_time}`")
        lines.append(f"- \u6e90\u6570: {len(latest_data.items)}")
        lines.append(f"- \u603b\u6761\u76ee: {latest_total_items}")
        lines.append(f"- failed_ids: {latest_data.failed_ids}")
        lines.append("")
        for source_id, items in latest_data.items.items():
            source_name = latest_data.id_to_name.get(source_id, source_id)
            lines.append(f"### {source_name} (`{source_id}`)")
            lines.append("")
            lines.append(f"- latest \u6761\u6570: {len(items)}")
            lines.append("")
            for index, item in enumerate(items, start=1):
                lines.append(f"{index}. [{item.rank}] {item.title}")
            lines.append("")
    else:
        lines.append("- latest \u8bfb\u56de\u4e3a\u7a7a")
        lines.append("")

    return "\n".join(lines)


def export_stage2_outbox(
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
    run_log: str,
) -> dict[str, object]:
    outbox_path = Path(outbox_dir)
    outbox_path.mkdir(parents=True, exist_ok=True)
    config_path_obj = Path(config_path)
    storage_path = Path(storage_data_dir)

    normalized_source_counts = {
        source.source_id: len(source.items)
        for source in normalized_batch.sources
    }
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
            "total_items": sum(normalized_source_counts.values()),
            "source_item_counts": normalized_source_counts,
        },
        "latest_readback": {
            "exists": latest_data is not None,
            "crawl_time": latest_data.crawl_time if latest_data else "",
            "source_count": len(latest_data.items) if latest_data else 0,
            "total_items": latest_data.get_total_count() if latest_data else 0,
            "failed_ids": list(latest_data.failed_ids) if latest_data else [],
            "failure_count": len(latest_data.failures) if latest_data else 0,
        },
    }

    _write_review_text(
        outbox_path / "stage2_crawl_batch.json",
        json.dumps(
            {"summary": summary, "batch": asdict(crawl_batch)},
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage2_normalized_batch.json",
        json.dumps(
            {"summary": summary, "batch": normalized_batch.to_dict()},
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage2_latest_news_data.json",
        json.dumps(
            {"summary": summary, "latest": latest_data.to_dict() if latest_data else None},
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_review_text(
        outbox_path / "stage2_review.md",
        _build_stage2_review_markdown(
            generated_at=generated_at,
            config_path=config_path_obj,
            storage_data_dir=storage_path,
            request_interval_ms=request_interval_ms,
            source_specs=source_specs,
            crawl_batch=crawl_batch,
            normalized_batch=normalized_batch,
            latest_data=latest_data,
        ),
    )
    _write_review_text(outbox_path / "stage2_run.log", run_log)
    return summary


def run_stage2_review(
    *,
    config_path: str | Path = "config/config.yaml",
    outbox_dir: str | Path = "outbox",
    storage_data_dir: str | Path | None = None,
) -> dict[str, object]:
    log_buffer = StringIO()
    resolved_config_path = Path(config_path).resolve()
    outbox_path = Path(outbox_dir)
    resolved_storage_dir = Path(storage_data_dir) if storage_data_dir else outbox_path / "stage2_storage"

    latest_data: NewsData | None = None

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
        finally:
            storage.cleanup()

    return export_stage2_outbox(
        outbox_dir=outbox_dir,
        generated_at=generated_at,
        config_path=resolved_config_path,
        storage_data_dir=resolved_storage_dir,
        request_interval_ms=request_interval_ms,
        source_specs=source_specs,
        crawl_batch=crawl_batch,
        normalized_batch=normalized_batch,
        latest_data=latest_data,
        run_log=log_buffer.getvalue(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run crawl -> normalize -> store validation and export stage-2 review artifacts.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--outbox", default="outbox")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_stage2_review(
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
