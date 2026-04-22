# coding=utf-8
"""Native helpers for detecting incremental snapshot titles."""

from __future__ import annotations

from typing import Optional

from newspulse.storage.base import NewsData
from newspulse.utils.logging import get_logger


logger = get_logger(__name__)


def detect_latest_new_title_map(
    latest_data: NewsData | None,
    all_data: NewsData | None,
    current_platform_ids: Optional[list[str]] = None,
) -> dict[str, set[str]]:
    """Return new titles from the latest crawl grouped by source."""

    if not latest_data or not latest_data.items:
        return {}

    latest_time = latest_data.crawl_time
    latest_titles = _collect_latest_titles(latest_data, current_platform_ids)
    if not latest_titles:
        return {}

    if not all_data or not all_data.items:
        return latest_titles

    historical_titles = _collect_historical_titles(
        all_data,
        latest_time=latest_time,
        current_platform_ids=current_platform_ids,
    )
    has_historical_data = any(titles for titles in historical_titles.values())
    if not has_historical_data:
        return latest_titles

    new_title_map: dict[str, set[str]] = {}
    for source_id, titles in latest_titles.items():
        unmatched = titles - historical_titles.get(source_id, set())
        if unmatched:
            new_title_map[source_id] = unmatched
    return new_title_map


def detect_latest_new_title_map_from_storage(
    storage_manager,
    current_platform_ids: Optional[list[str]] = None,
) -> dict[str, set[str]]:
    """Load storage data and return new titles from the latest crawl."""

    try:
        latest_data = storage_manager.get_latest_crawl_data()
        all_data = storage_manager.get_today_all_data()
    except Exception as exc:
        logger.exception("[snapshot] failed to load storage data for incremental titles")
        return {}

    return detect_latest_new_title_map(
        latest_data,
        all_data,
        current_platform_ids=current_platform_ids,
    )


def _collect_latest_titles(
    news_data: NewsData,
    current_platform_ids: Optional[list[str]] = None,
) -> dict[str, set[str]]:
    title_map: dict[str, set[str]] = {}
    for source_id, news_list in news_data.items.items():
        if current_platform_ids is not None and source_id not in current_platform_ids:
            continue
        titles = {
            (item.title or "").strip()
            for item in news_list
            if (item.title or "").strip()
        }
        if titles:
            title_map[source_id] = titles
    return title_map


def _collect_historical_titles(
    news_data: NewsData,
    *,
    latest_time: str,
    current_platform_ids: Optional[list[str]] = None,
) -> dict[str, set[str]]:
    title_map: dict[str, set[str]] = {}
    for source_id, news_list in news_data.items.items():
        if current_platform_ids is not None and source_id not in current_platform_ids:
            continue
        titles = title_map.setdefault(source_id, set())
        for item in news_list:
            title = (item.title or "").strip()
            first_time = item.first_time or item.crawl_time
            if title and first_time < latest_time:
                titles.add(title)
    return title_map
