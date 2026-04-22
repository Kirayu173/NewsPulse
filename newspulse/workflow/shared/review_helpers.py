# coding=utf-8
"""Shared helpers for stage review exporters."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
