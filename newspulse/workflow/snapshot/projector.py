# coding=utf-8
"""Projection helpers for building workflow snapshots."""

from __future__ import annotations

import hashlib
from typing import Dict

from newspulse.storage.base import NewsItem
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    SourceFailure,
    StandaloneSection,
)
from newspulse.workflow.snapshot.models import SnapshotProjection, SnapshotSourceBundle


class SnapshotProjector:
    """Project storage-backed bundle data into the workflow snapshot contract."""

    def __init__(
        self,
        *,
        standalone_platform_ids: list[str] | None = None,
        standalone_max_items: int = 20,
    ):
        self.standalone_platform_ids = list(standalone_platform_ids or [])
        self.standalone_max_items = standalone_max_items

    def build(self, bundle: SnapshotSourceBundle) -> SnapshotProjection:
        items = self._build_items(bundle)
        new_items = self._build_new_items(bundle)
        failed_sources = self._build_failed_sources(bundle)
        standalone_sections = self._build_standalone_sections(bundle)

        return SnapshotProjection(
            items=items,
            new_items=new_items,
            failed_sources=failed_sources,
            standalone_sections=standalone_sections,
            summary={
                "mode": bundle.mode,
                "generated_at": bundle.latest_crawl_time,
                "is_first_crawl": bundle.is_first_crawl,
                "latest_crawl_time": bundle.latest_crawl_time,
                "total_items": len(items),
                "total_new_items": len(new_items),
                "total_failed_sources": len(failed_sources),
                "total_standalone_sections": len(standalone_sections),
            },
        )

    def _build_items(self, bundle: SnapshotSourceBundle) -> list[HotlistItem]:
        source_index = self._select_primary_index(bundle)
        return self._flatten_index(source_index, bundle)

    def _build_new_items(self, bundle: SnapshotSourceBundle) -> list[HotlistItem]:
        source_index = self._filter_index_by_titles(bundle.latest_index, bundle.new_title_map)
        return self._flatten_index(source_index, bundle)

    def _build_failed_sources(self, bundle: SnapshotSourceBundle) -> list[SourceFailure]:
        latest_data = bundle.latest_data
        if not latest_data:
            return []

        if latest_data.failures:
            return [
                SourceFailure(
                    source_id=failure.source_id,
                    source_name=failure.source_name
                    or bundle.platform_names.get(failure.source_id, failure.source_id),
                    reason=failure.reason,
                    resolved_source_id=failure.resolved_source_id,
                    exception_type=failure.exception_type,
                    message=failure.message,
                    attempts=failure.attempts,
                )
                for failure in latest_data.failures
            ]

        return [
            SourceFailure(
                source_id=source_id,
                source_name=bundle.platform_names.get(source_id, source_id),
            )
            for source_id in latest_data.failed_ids
        ]

    def _build_standalone_sections(
        self,
        bundle: SnapshotSourceBundle,
    ) -> list[StandaloneSection]:
        if not self.standalone_platform_ids:
            return []

        if bundle.mode == "incremental":
            base_index = bundle.latest_index
        else:
            base_index = self._select_current_index(bundle)

        sections: list[StandaloneSection] = []
        for platform_id in self.standalone_platform_ids:
            platform_items = list(base_index.get(platform_id, {}).values())
            if not platform_items:
                continue

            hotlist_items = [
                self._to_hotlist_item(platform_id, item.title, item, bundle)
                for item in sorted(platform_items, key=self._standalone_sort_key)
            ]
            if self.standalone_max_items > 0:
                hotlist_items = hotlist_items[: self.standalone_max_items]

            sections.append(
                StandaloneSection(
                    key=platform_id,
                    label=bundle.platform_names.get(platform_id, platform_id),
                    items=hotlist_items,
                    metadata={"source_id": platform_id},
                )
            )
        return sections

    def _select_primary_index(
        self,
        bundle: SnapshotSourceBundle,
    ) -> Dict[str, Dict[str, NewsItem]]:
        if bundle.mode == "daily":
            return bundle.all_index
        if bundle.mode == "current":
            return self._select_current_index(bundle)
        if bundle.mode == "incremental":
            if bundle.is_first_crawl:
                return self._select_current_index(bundle)
            return self._filter_index_by_titles(bundle.latest_index, bundle.new_title_map)
        return bundle.all_index

    def _select_current_index(
        self,
        bundle: SnapshotSourceBundle,
    ) -> Dict[str, Dict[str, NewsItem]]:
        return self._filter_index_by_last_time(
            bundle.all_index,
            bundle.latest_crawl_time,
        )

    def _flatten_index(
        self,
        source_index: Dict[str, Dict[str, NewsItem]],
        bundle: SnapshotSourceBundle,
    ) -> list[HotlistItem]:
        items: list[HotlistItem] = []
        for source_id in sorted(source_index):
            for title in sorted(source_index[source_id]):
                items.append(
                    self._to_hotlist_item(
                        source_id,
                        title,
                        source_index[source_id][title],
                        bundle,
                    )
                )
        return items

    def _to_hotlist_item(
        self,
        source_id: str,
        title: str,
        item: NewsItem,
        bundle: SnapshotSourceBundle,
    ) -> HotlistItem:
        news_item_id = bundle.stable_ids.get((source_id, title))
        if not news_item_id:
            news_item_id = self._build_fallback_item_id(source_id, title)

        current_rank = item.rank or (item.ranks[-1] if item.ranks else 0)
        return HotlistItem(
            news_item_id=news_item_id,
            source_id=source_id,
            source_name=bundle.platform_names.get(source_id, item.source_name or source_id),
            title=title,
            url=item.url or "",
            mobile_url=item.mobile_url or "",
            current_rank=current_rank,
            ranks=list(item.ranks or ([item.rank] if item.rank else [])),
            first_time=item.first_time or item.crawl_time,
            last_time=item.last_time or item.crawl_time,
            count=item.count or 1,
            rank_timeline=list(item.rank_timeline or []),
            is_new=title in bundle.new_title_map.get(source_id, set()),
        )

    @staticmethod
    def _filter_index_by_last_time(
        source_index: Dict[str, Dict[str, NewsItem]],
        latest_time: str,
    ) -> Dict[str, Dict[str, NewsItem]]:
        if not latest_time:
            return source_index

        filtered: Dict[str, Dict[str, NewsItem]] = {}
        for source_id, items in source_index.items():
            current_items = {
                title: item
                for title, item in items.items()
                if (item.last_time or item.crawl_time) == latest_time
            }
            if current_items:
                filtered[source_id] = current_items
        return filtered

    @staticmethod
    def _filter_index_by_titles(
        source_index: Dict[str, Dict[str, NewsItem]],
        title_map: Dict[str, set[str]],
    ) -> Dict[str, Dict[str, NewsItem]]:
        if not title_map:
            return {}

        filtered: Dict[str, Dict[str, NewsItem]] = {}
        for source_id, titles in title_map.items():
            if source_id not in source_index:
                continue
            matched = {
                title: source_index[source_id][title]
                for title in titles
                if title in source_index[source_id]
            }
            if matched:
                filtered[source_id] = matched
        return filtered

    @staticmethod
    def _build_fallback_item_id(source_id: str, title: str) -> str:
        digest = hashlib.sha1(f"{source_id}:{title}".encode("utf-8")).hexdigest()[:16]
        return f"synthetic:{source_id}:{digest}"

    @staticmethod
    def _standalone_sort_key(item: NewsItem) -> tuple[int, str]:
        rank = item.rank if item.rank > 0 else 9999
        return (rank, item.title)
