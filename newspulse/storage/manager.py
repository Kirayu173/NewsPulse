# coding=utf-8
"""Storage manager facade for the local hotlist-only backend."""

from dataclasses import dataclass
from typing import Optional

from newspulse.storage.base import ArticleContentRecord, NewsData, NormalizedCrawlBatch, StorageBackend
from newspulse.storage.local import LocalStorageBackend
from newspulse.utils.logging import get_logger
from newspulse.utils.time import DEFAULT_TIMEZONE


logger = get_logger(__name__)


@dataclass(frozen=True)
class StorageManagerSettings:
    """Normalized settings used to build a storage manager instance."""

    backend_type: str = "local"
    data_dir: str = "output"
    enable_txt: bool = True
    enable_html: bool = True
    local_retention_days: int = 0
    timezone: str = DEFAULT_TIMEZONE

    def build(self) -> "StorageManager":
        return StorageManager(
            backend_type=self.backend_type,
            data_dir=self.data_dir,
            enable_txt=self.enable_txt,
            enable_html=self.enable_html,
            local_retention_days=self.local_retention_days,
            timezone=self.timezone,
        )


class StorageManager:
    def __init__(
        self,
        backend_type: str = "local",
        data_dir: str = "output",
        enable_txt: bool = True,
        enable_html: bool = True,
        local_retention_days: int = 0,
        timezone: str = DEFAULT_TIMEZONE,
    ):
        self.backend_type = backend_type
        self.data_dir = data_dir
        self.enable_txt = enable_txt
        self.enable_html = enable_html
        self.local_retention_days = local_retention_days
        self.timezone = timezone
        self._backend: Optional[StorageBackend] = None

    def get_backend(self) -> StorageBackend:
        if self._backend is None:
            if self.backend_type != "local":
                logger.warning(
                    "[storage] unsupported backend=%s; falling back to local storage",
                    self.backend_type,
                )

            self._backend = LocalStorageBackend(
                data_dir=self.data_dir,
                enable_txt=self.enable_txt,
                enable_html=self.enable_html,
                timezone=self.timezone,
            )
            logger.info("[storage] initialized local storage backend (data_dir=%s)", self.data_dir)

        return self._backend

    @property
    def backend(self) -> StorageBackend:
        return self.get_backend()

    @property
    def news_repo(self):
        return getattr(self.backend, "news_repo", None)

    @property
    def schedule_repo(self):
        return getattr(self.backend, "schedule_repo", None)

    @property
    def ai_filter_repo(self):
        return getattr(self.backend, "ai_filter_repo", None)

    @property
    def article_content_repo(self):
        return getattr(self.backend, "article_content_repo", None)

    def save_news_data(self, data: NewsData) -> bool:
        return self.backend.save_news_data(data)

    def save_normalized_crawl_batch(self, batch: NormalizedCrawlBatch) -> bool:
        return self.backend.save_normalized_crawl_batch(batch)

    def get_today_all_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        return self.backend.get_today_all_data(date)

    def get_latest_crawl_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        return self.backend.get_latest_crawl_data(date)

    def get_article_content(self, normalized_url: str, date: Optional[str] = None) -> Optional[ArticleContentRecord]:
        return self.backend.get_article_content(normalized_url, date)

    def save_article_content(self, record: ArticleContentRecord, date: Optional[str] = None) -> bool:
        return self.backend.save_article_content(record, date)

    def save_txt_snapshot(self, data: NewsData | NormalizedCrawlBatch) -> Optional[str]:
        return self.backend.save_txt_snapshot(data)

    def save_html_report(self, html_content: str, filename: str) -> Optional[str]:
        return self.backend.save_html_report(html_content, filename)

    def is_first_crawl_today(self, date: Optional[str] = None) -> bool:
        return self.backend.is_first_crawl_today(date)

    def cleanup(self) -> None:
        if self._backend:
            self._backend.cleanup()

    def cleanup_old_data(self) -> int:
        if self.local_retention_days <= 0:
            return 0
        return self.backend.cleanup_old_data(self.local_retention_days)

    @property
    def backend_name(self) -> str:
        return self.backend.backend_name

    @property
    def supports_txt(self) -> bool:
        return self.backend.supports_txt

    def has_period_executed(self, date_str: str, period_key: str, action: str) -> bool:
        return self.backend.has_period_executed(date_str, period_key, action)

    def record_period_execution(self, date_str: str, period_key: str, action: str) -> bool:
        return self.backend.record_period_execution(date_str, period_key, action)


def get_storage_manager(
    backend_type: str = "local",
    data_dir: str = "output",
    enable_txt: bool = True,
    enable_html: bool = True,
    local_retention_days: int = 0,
    timezone: str = DEFAULT_TIMEZONE,
) -> StorageManager:
    return StorageManagerSettings(
        backend_type=backend_type,
        data_dir=data_dir,
        enable_txt=enable_txt,
        enable_html=enable_html,
        local_retention_days=local_retention_days,
        timezone=timezone,
    ).build()
