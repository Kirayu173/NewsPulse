# coding=utf-8
"""Private models used by the snapshot stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.shared.contracts import HotlistItem, SourceFailure, StandaloneSection


@dataclass(frozen=True)
class SnapshotSourceBundle:
    """Storage-backed source bundle used to build a workflow snapshot."""

    mode: str
    latest_data: NewsData | None
    all_data: NewsData | None
    is_first_crawl: bool
    latest_crawl_time: str = ""
    stable_ids: Dict[tuple[str, str], str] = field(default_factory=dict)
    platform_names: Dict[str, str] = field(default_factory=dict)
    latest_index: Dict[str, Dict[str, NewsItem]] = field(default_factory=dict)
    all_index: Dict[str, Dict[str, NewsItem]] = field(default_factory=dict)
    new_title_map: Dict[str, set[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SnapshotProjection:
    """Projected snapshot content built from a source bundle."""

    items: list[HotlistItem] = field(default_factory=list)
    new_items: list[HotlistItem] = field(default_factory=list)
    failed_sources: list[SourceFailure] = field(default_factory=list)
    standalone_sections: list[StandaloneSection] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
