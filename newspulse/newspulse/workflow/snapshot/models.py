# coding=utf-8
"""Private models used by the snapshot stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from newspulse.storage.base import NewsData, NewsItem


@dataclass(frozen=True)
class SnapshotSourceBundle:
    """Storage-backed source bundle used to build a workflow snapshot."""

    mode: str
    latest_data: NewsData | None
    all_data: NewsData | None
    is_first_crawl: bool
    stable_ids: Dict[tuple[str, str], str] = field(default_factory=dict)
    platform_names: Dict[str, str] = field(default_factory=dict)
    latest_index: Dict[str, Dict[str, NewsItem]] = field(default_factory=dict)
    all_index: Dict[str, Dict[str, NewsItem]] = field(default_factory=dict)
    new_titles: Dict[str, Dict[str, dict]] = field(default_factory=dict)
