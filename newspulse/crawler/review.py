# coding=utf-8
"""Stage-only crawl review exporter for manual inspection."""

from __future__ import annotations

import argparse
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Sequence

from newspulse.core import load_config
from newspulse.crawler.fetcher import DataFetcher
from newspulse.crawler.models import CrawlBatchResult, CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name

REVIEW_FILE_ENCODING = "utf-8-sig"


def _write_review_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=REVIEW_FILE_ENCODING)


def _build_source_specs(platforms: Sequence[dict]) -> list[CrawlSourceSpec]:
    return [
        CrawlSourceSpec(
            source_id=str(platform["id"]),
            source_name=resolve_source_display_name(
                str(platform["id"]),
                str(platform.get("name", "") or ""),
            ),
        )
        for platform in platforms
        if platform.get("id")
    ]


def _build_crawl_review_markdown(
    *,
    generated_at: datetime,
    request_interval_ms: int,
    source_specs: Sequence[CrawlSourceSpec],
    crawl_batch: CrawlBatchResult,
) -> str:
    lines: list[str] = []
    lines.append("# Crawl Review")
    lines.append("")
    lines.append(
        f"- \u751f\u6210\u65f6\u95f4: {generated_at.strftime('%Y-%m-%d %H:%M:%S %z')}"
    )
    lines.append(f"- \u8bf7\u6c42\u95f4\u9694: {request_interval_ms} ms")
    lines.append(f"- \u8bf7\u6c42\u6e90\u6570: {len(source_specs)}")
    lines.append(f"- \u6210\u529f: {len(crawl_batch.sources)}")
    lines.append(f"- \u5931\u8d25: {len(crawl_batch.failures)}")
    lines.append("")
    lines.append("## Requested Sources")
    lines.append("")

    for spec in source_specs:
        lines.append(f"- `{spec.source_id}` / {spec.source_name}")

    lines.append("")
    lines.append("## Successful Sources")
    lines.append("")

    if crawl_batch.sources:
        for source in crawl_batch.sources:
            lines.append(f"### {source.source_name} (`{source.source_id}`)")
            lines.append("")
            lines.append(f"- \u6293\u53d6\u6761\u6570: {len(source.items)}")
            lines.append(f"- \u89e3\u6790\u6e90 ID: `{source.resolved_source_id}`")
            lines.append(f"- \u5c1d\u8bd5\u6b21\u6570: {source.attempts}")
            lines.append("")
            for index, item in enumerate(source.items, start=1):
                lines.append(f"{index}. {item.title.strip()}")
                if item.url:
                    lines.append(f"   - URL: {item.url.strip()}")
                if item.mobile_url and item.mobile_url != item.url:
                    lines.append(f"   - Mobile: {item.mobile_url.strip()}")
            lines.append("")
    else:
        lines.append("- \u65e0\u6210\u529f\u6e90")
        lines.append("")

    lines.append("## Failed Sources")
    lines.append("")
    if crawl_batch.failures:
        for failure in crawl_batch.failures:
            lines.append(f"- `{failure.source_id}` / {failure.source_name}")
            lines.append(f"  - resolved_source_id: `{failure.resolved_source_id}`")
            lines.append(f"  - exception: `{failure.exception_type}`")
            lines.append(f"  - message: {failure.message}")
            lines.append(f"  - attempts: {failure.attempts}")
    else:
        lines.append("- \u65e0\u5931\u8d25\u6e90")
    lines.append("")
    return "\n".join(lines)


def export_crawl_outbox(
    *,
    outbox_dir: str | Path,
    generated_at: datetime,
    request_interval_ms: int,
    source_specs: Sequence[CrawlSourceSpec],
    crawl_batch: CrawlBatchResult,
    crawl_log: str,
) -> dict[str, object]:
    outbox_path = Path(outbox_dir)
    outbox_path.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": generated_at.isoformat(),
        "requested_sources": [asdict(spec) for spec in source_specs],
        "request_interval_ms": request_interval_ms,
        "success_count": len(crawl_batch.sources),
        "failure_count": len(crawl_batch.failures),
        "successful_source_ids": crawl_batch.successful_source_ids,
        "failed_source_ids": crawl_batch.failed_source_ids,
    }
    batch_payload = {
        "summary": summary,
        "batch": asdict(crawl_batch),
    }

    _write_review_text(
        outbox_path / "crawl_batch.json",
        json.dumps(batch_payload, ensure_ascii=False, indent=2),
    )
    _write_review_text(
        outbox_path / "crawl_review.md",
        _build_crawl_review_markdown(
            generated_at=generated_at,
            request_interval_ms=request_interval_ms,
            source_specs=source_specs,
            crawl_batch=crawl_batch,
        ),
    )
    _write_review_text(outbox_path / "crawl_run.log", crawl_log)
    return summary


def run_crawl_review(
    *,
    config_path: str | Path = "config/config.yaml",
    outbox_dir: str | Path = "outbox",
) -> dict[str, object]:
    log_buffer = StringIO()

    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        config = load_config(str(config_path))
        source_specs = _build_source_specs(config["PLATFORMS"])
        request_interval_ms = int(config["REQUEST_INTERVAL"])
        proxy_url = config["DEFAULT_PROXY"] if config.get("USE_PROXY") else None
        crawl_batch = DataFetcher(proxy_url=proxy_url).crawl(
            source_specs,
            request_interval=request_interval_ms,
        )

    generated_at = datetime.now().astimezone()
    return export_crawl_outbox(
        outbox_dir=outbox_dir,
        generated_at=generated_at,
        request_interval_ms=request_interval_ms,
        source_specs=source_specs,
        crawl_batch=crawl_batch,
        crawl_log=log_buffer.getvalue(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run crawl-only validation and export review artifacts.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--outbox", default="outbox")
    args = parser.parse_args(list(argv) if argv is not None else None)

    summary = run_crawl_review(config_path=args.config, outbox_dir=args.outbox)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
