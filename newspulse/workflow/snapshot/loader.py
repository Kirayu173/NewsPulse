# coding=utf-8
"""Storage loading helpers for the snapshot stage."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from newspulse.storage.base import NewsData, NewsItem
from newspulse.workflow.snapshot.history import detect_latest_new_title_map
from newspulse.workflow.snapshot.models import SnapshotSourceBundle


class SnapshotBundleLoader:
    """Load storage state and derive the native bundle for snapshot projection."""

    def __init__(
        self,
        storage_manager: Any,
        *,
        platform_ids: list[str] | None = None,
        platform_names: Mapping[str, str] | None = None,
    ):
        self.storage_manager = storage_manager
        self.platform_ids = list(platform_ids or [])
        self.platform_names = dict(platform_names or {})

    def load(self, mode: str) -> SnapshotSourceBundle:
        latest_data = self.storage_manager.get_latest_crawl_data()
        all_data = self.storage_manager.get_today_all_data()
        latest_crawl_time = (
            latest_data.crawl_time
            if latest_data
            else (all_data.crawl_time if all_data else "")
        )

        latest_index = self._index_news_data(latest_data)
        all_index = self._index_news_data(all_data)
        platform_names = self._build_platform_names(latest_data, all_data)

        return SnapshotSourceBundle(
            mode=mode,
            latest_data=latest_data,
            all_data=all_data,
            is_first_crawl=bool(self.storage_manager.is_first_crawl_today()),
            latest_crawl_time=latest_crawl_time,
            stable_ids=self._load_stable_ids(),
            platform_names=platform_names,
            latest_index=latest_index,
            all_index=all_index,
            new_title_map=detect_latest_new_title_map(
                latest_data,
                all_data,
                current_platform_ids=self.platform_ids or None,
            ),
        )

    def _build_platform_names(
        self,
        latest_data: NewsData | None,
        all_data: NewsData | None,
    ) -> dict[str, str]:
        platform_names = dict(self.platform_names)
        if latest_data:
            platform_names.update(latest_data.id_to_name)
        if all_data:
            platform_names.update(all_data.id_to_name)
        return platform_names

    def _index_news_data(self, news_data: NewsData | None) -> Dict[str, Dict[str, NewsItem]]:
        if not news_data or not news_data.items:
            return {}

        indexed: Dict[str, Dict[str, NewsItem]] = {}
        for source_id, news_list in news_data.items.items():
            if self.platform_ids and source_id not in self.platform_ids:
                continue
            source_index = indexed.setdefault(source_id, {})
            for item in news_list:
                title = (item.title or "").strip()
                if not title:
                    continue
                source_index[title] = item
        return indexed

    def _load_stable_ids(self) -> Dict[tuple[str, str], str]:
        stable_ids: Dict[tuple[str, str], str] = {}
        for item in self.storage_manager.get_all_news_ids():
            source_id = str(item.get("source_id", "")).strip()
            title = str(item.get("title", "")).strip()
            raw_id = item.get("id")
            if not source_id or not title or raw_id is None:
                continue

            key = (source_id, title)
            candidate = str(raw_id)
            existing = stable_ids.get(key)
            if existing is None:
                stable_ids[key] = candidate
                continue

            if candidate.isdigit() and existing.isdigit() and int(candidate) < int(existing):
                stable_ids[key] = candidate

        return stable_ids
