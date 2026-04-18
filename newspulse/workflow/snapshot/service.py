# coding=utf-8
"""Snapshot stage service."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping

from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.snapshot.history import detect_latest_new_titles_from_storage
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    SourceFailure,
    StandaloneSection,
)
from newspulse.workflow.shared.options import SnapshotOptions
from newspulse.workflow.snapshot.models import SnapshotSourceBundle


class SnapshotService:
    """Build the unique downstream snapshot from persisted hotlist data."""

    def __init__(
        self,
        storage_manager: Any,
        *,
        platform_ids: list[str] | None = None,
        platform_names: Mapping[str, str] | None = None,
        standalone_platform_ids: list[str] | None = None,
        standalone_max_items: int = 20,
    ):
        self.storage_manager = storage_manager
        self.platform_ids = list(platform_ids or [])
        self.platform_names = dict(platform_names or {})
        self.standalone_platform_ids = list(standalone_platform_ids or [])
        self.standalone_max_items = standalone_max_items

    def build(self, options: SnapshotOptions) -> HotlistSnapshot:
        """Build a normalized workflow snapshot for the requested report mode."""

        bundle = self._load_bundle(options.mode)
        generated_at = bundle.latest_data.crawl_time if bundle.latest_data else ""

        items = self._build_items(bundle)
        new_items = self._build_new_items(bundle)
        failed_sources = self._build_failed_sources(bundle)
        standalone_sections = self._build_standalone_sections(bundle)

        summary = {
            "mode": options.mode,
            "generated_at": generated_at,
            "is_first_crawl": bundle.is_first_crawl,
            "latest_crawl_time": generated_at,
            "total_items": len(items),
            "total_new_items": len(new_items),
            "total_failed_sources": len(failed_sources),
            "total_standalone_sections": len(standalone_sections),
        }

        return HotlistSnapshot(
            mode=options.mode,
            generated_at=generated_at,
            items=items,
            failed_sources=failed_sources,
            new_items=new_items,
            standalone_sections=standalone_sections,
            summary=summary,
        )

    def _load_bundle(self, mode: str) -> SnapshotSourceBundle:
        latest_data = self.storage_manager.get_latest_crawl_data()
        all_data = self.storage_manager.get_today_all_data()
        is_first_crawl = bool(self.storage_manager.is_first_crawl_today())

        latest_index = self._index_news_data(latest_data)
        all_index = self._index_news_data(all_data)

        platform_names = dict(self.platform_names)
        if latest_data:
            platform_names.update(latest_data.id_to_name)
        if all_data:
            platform_names.update(all_data.id_to_name)

        return SnapshotSourceBundle(
            mode=mode,
            latest_data=latest_data,
            all_data=all_data,
            is_first_crawl=is_first_crawl,
            stable_ids=self._load_stable_ids(),
            platform_names=platform_names,
            latest_index=latest_index,
            all_index=all_index,
            new_titles=detect_latest_new_titles_from_storage(self.storage_manager, self.platform_ids or None),
        )

    def _build_items(self, bundle: SnapshotSourceBundle) -> list[HotlistItem]:
        if bundle.mode == "daily":
            source_index = bundle.all_index
        elif bundle.mode == "current":
            latest_time = bundle.latest_data.crawl_time if bundle.latest_data else ""
            source_index = self._filter_index_by_last_time(bundle.all_index, latest_time)
        elif bundle.mode == "incremental":
            if bundle.is_first_crawl:
                source_index = bundle.latest_index
            else:
                source_index = self._filter_index_by_titles(bundle.latest_index, bundle.new_titles)
        else:
            source_index = bundle.all_index

        return self._flatten_index(source_index, bundle)

    def _build_new_items(self, bundle: SnapshotSourceBundle) -> list[HotlistItem]:
        source_index = self._filter_index_by_titles(bundle.latest_index, bundle.new_titles)
        return self._flatten_index(source_index, bundle)

    def _build_failed_sources(self, bundle: SnapshotSourceBundle) -> list[SourceFailure]:
        failed_ids = bundle.latest_data.failed_ids if bundle.latest_data else []
        return [
            SourceFailure(
                source_id=source_id,
                source_name=bundle.platform_names.get(source_id, source_id),
            )
            for source_id in failed_ids
        ]

    def _build_standalone_sections(self, bundle: SnapshotSourceBundle) -> list[StandaloneSection]:
        if not self.standalone_platform_ids:
            return []

        if bundle.mode == "incremental":
            base_index = bundle.latest_index
        else:
            latest_time = bundle.latest_data.crawl_time if bundle.latest_data else ""
            base_index = self._filter_index_by_last_time(bundle.all_index, latest_time)

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

    def _flatten_index(
        self,
        source_index: Dict[str, Dict[str, NewsItem]],
        bundle: SnapshotSourceBundle,
    ) -> list[HotlistItem]:
        items: list[HotlistItem] = []
        for source_id in sorted(source_index):
            for title in sorted(source_index[source_id]):
                items.append(self._to_hotlist_item(source_id, title, source_index[source_id][title], bundle))
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

        new_titles_for_source = bundle.new_titles.get(source_id, {})
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
            is_new=title in new_titles_for_source,
        )

    def _index_news_data(self, news_data: NewsData | None) -> Dict[str, Dict[str, NewsItem]]:
        if not news_data or not news_data.items:
            return {}

        indexed: Dict[str, Dict[str, NewsItem]] = {}
        for source_id, news_list in news_data.items.items():
            if self.platform_ids and source_id not in self.platform_ids:
                continue
            source_index = indexed.setdefault(source_id, {})
            for item in news_list:
                source_index[item.title] = item
        return indexed

    def _filter_index_by_last_time(
        self,
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

    def _filter_index_by_titles(
        self,
        source_index: Dict[str, Dict[str, NewsItem]],
        titles_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, NewsItem]]:
        if not titles_map:
            return {}

        filtered: Dict[str, Dict[str, NewsItem]] = {}
        for source_id, titles in titles_map.items():
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

    def _load_stable_ids(self) -> Dict[tuple[str, str], str]:
        stable_ids: Dict[tuple[str, str], str] = {}
        all_news_ids = self.storage_manager.get_all_news_ids()
        for item in all_news_ids:
            source_id = str(item.get("source_id", "")).strip()
            title = str(item.get("title", "")).strip()
            raw_id = item.get("id")
            if not source_id or not title or raw_id is None:
                continue
            key = (source_id, title)
            candidate = str(raw_id)
            if key not in stable_ids:
                stable_ids[key] = candidate
                continue
            if candidate.isdigit() and stable_ids[key].isdigit():
                if int(candidate) < int(stable_ids[key]):
                    stable_ids[key] = candidate
        return stable_ids

    @staticmethod
    def _build_fallback_item_id(source_id: str, title: str) -> str:
        digest = hashlib.sha1(f"{source_id}:{title}".encode("utf-8")).hexdigest()[:16]
        return f"synthetic:{source_id}:{digest}"

    @staticmethod
    def _standalone_sort_key(item: NewsItem) -> tuple[int, str]:
        rank = item.rank if item.rank > 0 else 9999
        return (rank, item.title)
