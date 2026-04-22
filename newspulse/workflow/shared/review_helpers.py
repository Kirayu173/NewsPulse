# coding=utf-8
"""Shared helpers for stage review exporters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from newspulse.crawler.models import CrawlSourceSpec
from newspulse.crawler.source_names import resolve_source_display_name


REVIEW_FILE_ENCODING = "utf-8-sig"


def write_review_text(path: Path, content: str, *, encoding: str = REVIEW_FILE_ENCODING) -> None:
    """Write a review artifact with the project-default encoding."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


def build_source_specs(platforms: Sequence[dict]) -> list[CrawlSourceSpec]:
    """Normalize configured platform rows into crawl source specs."""

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


def build_review_payload(summary: Mapping[str, Any], **payload: Any) -> dict[str, Any]:
    """Wrap a stage artifact payload with its review summary."""

    return {
        "summary": dict(summary),
        **payload,
    }


class ReviewOutboxWriter:
    """Helper for consistent stage review artifact export."""

    def __init__(self, outbox_dir: str | Path):
        self.path = Path(outbox_dir)
        self.path.mkdir(parents=True, exist_ok=True)

    def write_json(self, filename: str | Path, payload: Mapping[str, Any]) -> None:
        write_review_text(
            self.path / filename,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def write_stage_json(
        self,
        filename: str | Path,
        *,
        summary: Mapping[str, Any],
        **payload: Any,
    ) -> None:
        self.write_json(filename, build_review_payload(summary, **payload))

    def write_markdown(self, filename: str | Path, content: str) -> None:
        write_review_text(self.path / filename, content)

    def write_log(self, filename: str | Path, content: str) -> None:
        write_review_text(self.path / filename, content)
