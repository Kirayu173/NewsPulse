# coding=utf-8
"""Storage manager facade for the local hotlist-only backend."""

from typing import Optional

from newspulse.storage.base import NewsData, NormalizedCrawlBatch, StorageBackend
from newspulse.storage.local import LocalStorageBackend
from newspulse.utils.time import DEFAULT_TIMEZONE


_storage_manager: Optional["StorageManager"] = None


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
                print(f"[存储管理器] 已移除远程存储，忽略 backend={self.backend_type}，改用本地存储")

            self._backend = LocalStorageBackend(
                data_dir=self.data_dir,
                enable_txt=self.enable_txt,
                enable_html=self.enable_html,
                timezone=self.timezone,
            )
            print(f"[存储管理器] 使用本地存储后端 (数据目录: {self.data_dir})")

        return self._backend

    def save_news_data(self, data: NewsData) -> bool:
        return self.get_backend().save_news_data(data)

    def save_normalized_crawl_batch(self, batch: NormalizedCrawlBatch) -> bool:
        return self.get_backend().save_normalized_crawl_batch(batch)

    def get_today_all_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        return self.get_backend().get_today_all_data(date)

    def get_latest_crawl_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        return self.get_backend().get_latest_crawl_data(date)

    def detect_new_titles(self, current_data: NewsData) -> dict:
        return self.get_backend().detect_new_titles(current_data)

    def save_txt_snapshot(self, data: NewsData | NormalizedCrawlBatch) -> Optional[str]:
        return self.get_backend().save_txt_snapshot(data)

    def save_html_report(self, html_content: str, filename: str) -> Optional[str]:
        return self.get_backend().save_html_report(html_content, filename)

    def is_first_crawl_today(self, date: Optional[str] = None) -> bool:
        return self.get_backend().is_first_crawl_today(date)

    def cleanup(self) -> None:
        if self._backend:
            self._backend.cleanup()

    def cleanup_old_data(self) -> int:
        total_deleted = 0
        if self.local_retention_days > 0:
            total_deleted += self.get_backend().cleanup_old_data(self.local_retention_days)
        return total_deleted

    @property
    def backend_name(self) -> str:
        return self.get_backend().backend_name

    @property
    def supports_txt(self) -> bool:
        return self.get_backend().supports_txt

    def has_period_executed(self, date_str: str, period_key: str, action: str) -> bool:
        return self.get_backend().has_period_executed(date_str, period_key, action)

    def record_period_execution(self, date_str: str, period_key: str, action: str) -> bool:
        return self.get_backend().record_period_execution(date_str, period_key, action)

    def begin_batch(self):
        self.get_backend().begin_batch()

    def end_batch(self):
        self.get_backend().end_batch()

    def get_active_ai_filter_tags(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().get_active_ai_filter_tags(date, interests_file)

    def get_latest_prompt_hash(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().get_latest_prompt_hash(date, interests_file)

    def get_latest_ai_filter_tag_version(self, date=None):
        return self.get_backend().get_latest_ai_filter_tag_version(date)

    def deprecate_all_ai_filter_tags(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().deprecate_all_ai_filter_tags(date, interests_file)

    def save_ai_filter_tags(self, tags, version, prompt_hash, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().save_ai_filter_tags(tags, version, prompt_hash, date, interests_file)

    def save_ai_filter_results(self, results, date=None):
        return self.get_backend().save_ai_filter_results(results, date)

    def get_active_ai_filter_results(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().get_active_ai_filter_results(date, interests_file)

    def deprecate_specific_ai_filter_tags(self, tag_ids, date=None):
        return self.get_backend().deprecate_specific_ai_filter_tags(tag_ids, date)

    def update_ai_filter_tags_hash(self, interests_file, new_hash, date=None):
        return self.get_backend().update_ai_filter_tags_hash(interests_file, new_hash, date)

    def update_ai_filter_tag_descriptions(self, tag_updates, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().update_ai_filter_tag_descriptions(tag_updates, date, interests_file)

    def update_ai_filter_tag_priorities(self, tag_priorities, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().update_ai_filter_tag_priorities(tag_priorities, date, interests_file)

    def save_analyzed_news(self, news_ids, source_type, interests_file, prompt_hash, matched_ids, date=None):
        return self.get_backend().save_analyzed_news(news_ids, source_type, interests_file, prompt_hash, matched_ids, date)

    def get_analyzed_news_ids(self, source_type="hotlist", date=None, interests_file="ai_interests.txt"):
        return self.get_backend().get_analyzed_news_ids(source_type, date, interests_file)

    def clear_analyzed_news(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().clear_analyzed_news(date, interests_file)

    def clear_unmatched_analyzed_news(self, date=None, interests_file="ai_interests.txt"):
        return self.get_backend().clear_unmatched_analyzed_news(date, interests_file)

    def get_all_news_ids(self, date=None):
        return self.get_backend().get_all_news_ids(date)


def get_storage_manager(
    backend_type: str = "local",
    data_dir: str = "output",
    enable_txt: bool = True,
    enable_html: bool = True,
    local_retention_days: int = 0,
    timezone: str = DEFAULT_TIMEZONE,
    force_new: bool = False,
) -> StorageManager:
    global _storage_manager

    if _storage_manager is None or force_new:
        _storage_manager = StorageManager(
            backend_type=backend_type,
            data_dir=data_dir,
            enable_txt=enable_txt,
            enable_html=enable_html,
            local_retention_days=local_retention_days,
            timezone=timezone,
        )

    return _storage_manager
