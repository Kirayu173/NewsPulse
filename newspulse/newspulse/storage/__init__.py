# coding=utf-8
"""Storage package exports for the hotlist-only runtime."""

from newspulse.storage.base import StorageBackend, NewsData, NewsItem, convert_crawl_results_to_news_data
from newspulse.storage.local import LocalStorageBackend
from newspulse.storage.manager import StorageManager, get_storage_manager
from newspulse.storage.repos import AIFilterRepository, NewsRepository, ScheduleRepository
from newspulse.storage.sqlite_mixin import SQLiteStorageMixin
from newspulse.storage.sqlite_runtime import SQLiteRuntime

__all__ = [
    "StorageBackend",
    "NewsItem",
    "NewsData",
    "SQLiteStorageMixin",
    "SQLiteRuntime",
    "convert_crawl_results_to_news_data",
    "LocalStorageBackend",
    "NewsRepository",
    "ScheduleRepository",
    "AIFilterRepository",
    "StorageManager",
    "get_storage_manager",
]
