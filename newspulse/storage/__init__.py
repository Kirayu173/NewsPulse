# coding=utf-8
"""Storage package exports for the hotlist-only runtime."""

from newspulse.storage.base import (
    ArticleContentRecord,
    NewsData,
    NewsItem,
    NormalizedCrawlBatch,
    NormalizedSourceBatch,
    SourceFailureRecord,
    StorageBackend,
    convert_crawl_batch_to_news_data,
    convert_news_data_to_normalized_batch,
    normalize_crawl_batch,
)
from newspulse.storage.local import LocalStorageBackend
from newspulse.storage.manager import StorageManager, get_storage_manager
from newspulse.storage.repos import AIFilterRepository, ArticleContentRepository, NewsRepository, ScheduleRepository
from newspulse.storage.sqlite_runtime import SQLiteRuntime

__all__ = [
    "StorageBackend",
    "ArticleContentRecord",
    "NewsItem",
    "NewsData",
    "SourceFailureRecord",
    "NormalizedSourceBatch",
    "NormalizedCrawlBatch",
    "SQLiteRuntime",
    "convert_crawl_batch_to_news_data",
    "convert_news_data_to_normalized_batch",
    "normalize_crawl_batch",
    "LocalStorageBackend",
    "NewsRepository",
    "ScheduleRepository",
    "AIFilterRepository",
    "ArticleContentRepository",
    "StorageManager",
    "get_storage_manager",
]
