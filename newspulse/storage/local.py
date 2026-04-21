# coding=utf-8
"""Local SQLite storage backend."""

import pytz
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from newspulse.storage.base import (
    ArticleContentRecord,
    NewsData,
    NormalizedCrawlBatch,
    StorageBackend,
    convert_news_data_to_normalized_batch,
)
from newspulse.storage.repos import AIFilterRepository, ArticleContentRepository, NewsRepository, ScheduleRepository
from newspulse.storage.sqlite_runtime import SQLiteRuntime
from newspulse.utils.time import DEFAULT_TIMEZONE


class LocalStorageBackend(StorageBackend):
    """Persist NewsPulse hotlist data to local SQLite files plus optional snapshots."""

    def __init__(
        self,
        data_dir: str = "output",
        enable_txt: bool = True,
        enable_html: bool = True,
        timezone: str = DEFAULT_TIMEZONE,
    ):
        self.runtime = SQLiteRuntime(data_dir=data_dir, timezone=timezone)
        self.data_dir = self.runtime.data_dir
        self.enable_txt = enable_txt
        self.enable_html = enable_html
        self.timezone = self.runtime.timezone
        self._db_connections = self.runtime.db_connections

        self.news_repo = NewsRepository(self.runtime)
        self.schedule_repo = ScheduleRepository(self.runtime)
        self.ai_filter_repo = AIFilterRepository(self.runtime)
        self.article_content_repo = ArticleContentRepository(self.runtime)

    @property
    def backend_name(self) -> str:
        return "local"

    @property
    def supports_txt(self) -> bool:
        return self.enable_txt

    def _get_configured_time(self) -> datetime:
        return self.runtime.get_configured_time()

    def _format_date_folder(self, date: Optional[str] = None) -> str:
        return self.runtime.format_date_folder(date)

    def _get_db_path(self, date: Optional[str] = None, db_type: str = "news") -> Path:
        return self.runtime.get_db_path(date, db_type)

    def _resolve_read_date(
        self,
        date: Optional[str] = None,
        *,
        db_type: str = "news",
        fallback_to_latest: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """Resolve a readable database date for read-only APIs."""

        if date is not None:
            return self._get_db_path(date, db_type).exists(), date

        current_path = self._get_db_path(None, db_type)
        if current_path.exists():
            return True, None
        if not fallback_to_latest:
            return False, None

        db_dir = self.data_dir / db_type
        if not db_dir.exists():
            return False, None

        latest_stem = ""
        for db_file in db_dir.glob("*.db"):
            stem = db_file.stem
            if re.match(r"^\d{4}-\d{2}-\d{2}$", stem) and stem > latest_stem:
                latest_stem = stem
        if not latest_stem:
            return False, None
        return True, latest_stem

    def save_normalized_crawl_batch(self, batch: NormalizedCrawlBatch) -> bool:
        db_path = self._get_db_path(batch.date)
        if not db_path.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)

        success, new_count, updated_count, title_changed_count, off_list_count = (
            self.news_repo._save_normalized_crawl_batch_impl(batch, "[本地存储]")
        )

        if success:
            log_parts = [f"[本地存储] 处理完成：新增 {new_count} 条"]
            if updated_count > 0:
                log_parts.append(f"更新 {updated_count} 条")
            if title_changed_count > 0:
                log_parts.append(f"标题变更 {title_changed_count} 条")
            if off_list_count > 0:
                log_parts.append(f"脱榜 {off_list_count} 条")
            print("；".join(log_parts))

        return success

    def save_news_data(self, data: NewsData) -> bool:
        return self.save_normalized_crawl_batch(convert_news_data_to_normalized_batch(data))

    def get_today_all_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        exists, resolved_date = self._resolve_read_date(date)
        if not exists:
            return None
        return self.news_repo._get_today_all_data_impl(resolved_date)

    def get_latest_crawl_data(self, date: Optional[str] = None) -> Optional[NewsData]:
        exists, resolved_date = self._resolve_read_date(date)
        if not exists:
            return None
        return self.news_repo._get_latest_crawl_data_impl(resolved_date)

    def get_article_content(self, normalized_url: str, date: Optional[str] = None) -> Optional[ArticleContentRecord]:
        exists, resolved_date = self._resolve_read_date(date, fallback_to_latest=False)
        if date is not None and not exists:
            return None
        return self.article_content_repo._get_by_normalized_url_impl(normalized_url, resolved_date)

    def save_article_content(self, record: ArticleContentRecord, date: Optional[str] = None) -> bool:
        return self.article_content_repo._save_impl(record, date)

    def detect_new_titles(self, current_data: NewsData) -> Dict[str, Dict]:
        return self.news_repo._detect_new_titles_impl(current_data)

    def is_first_crawl_today(self, date: Optional[str] = None) -> bool:
        db_path = self._get_db_path(date)
        if not db_path.exists():
            return True
        return self.news_repo._is_first_crawl_today_impl(date)

    def get_crawl_times(self, date: Optional[str] = None) -> List[str]:
        exists, resolved_date = self._resolve_read_date(date)
        if not exists:
            return []
        return self.news_repo._get_crawl_times_impl(resolved_date)

    def has_period_executed(self, date_str: str, period_key: str, action: str) -> bool:
        return self.schedule_repo._has_period_executed_impl(date_str, period_key, action)

    def record_period_execution(self, date_str: str, period_key: str, action: str) -> bool:
        success = self.schedule_repo._record_period_execution_impl(date_str, period_key, action)
        if success:
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[本地存储] 时间段执行记录已保存: {period_key}/{action} at {now_str}")
        return success

    def get_active_ai_filter_tags(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._get_active_tags_impl(date, interests_file)

    def get_latest_prompt_hash(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._get_latest_prompt_hash_impl(date, interests_file)

    def get_latest_ai_filter_tag_version(self, date=None):
        return self.ai_filter_repo._get_latest_tag_version_impl(date)

    def deprecate_all_ai_filter_tags(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._deprecate_all_tags_impl(date, interests_file)

    def save_ai_filter_tags(self, tags, version, prompt_hash, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._save_tags_impl(date, tags, version, prompt_hash, interests_file)

    def save_ai_filter_results(self, results, date=None):
        return self.ai_filter_repo._save_filter_results_impl(date, results)

    def get_active_ai_filter_results(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._get_active_filter_results_impl(date, interests_file)

    def deprecate_specific_ai_filter_tags(self, tag_ids, date=None):
        return self.ai_filter_repo._deprecate_specific_tags_impl(date, tag_ids)

    def update_ai_filter_tags_hash(self, interests_file, new_hash, date=None):
        return self.ai_filter_repo._update_tags_hash_impl(date, interests_file, new_hash)

    def update_ai_filter_tag_descriptions(self, tag_updates, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._update_tag_descriptions_impl(date, tag_updates, interests_file)

    def update_ai_filter_tag_priorities(self, tag_priorities, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._update_tag_priorities_impl(date, tag_priorities, interests_file)

    def save_analyzed_news(self, news_ids, source_type, interests_file, prompt_hash, matched_ids, date=None):
        return self.ai_filter_repo._save_analyzed_news_impl(
            date,
            news_ids,
            source_type,
            interests_file,
            prompt_hash,
            matched_ids,
        )

    def get_analyzed_news_ids(self, source_type="hotlist", date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._get_analyzed_news_ids_impl(date, source_type, interests_file)

    def clear_analyzed_news(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._clear_analyzed_news_impl(date, interests_file)

    def clear_unmatched_analyzed_news(self, date=None, interests_file="ai_interests.txt"):
        return self.ai_filter_repo._clear_unmatched_analyzed_news_impl(date, interests_file)

    def get_all_news_ids(self, date=None):
        exists, resolved_date = self._resolve_read_date(date)
        if not exists:
            return []
        return self.news_repo._get_all_news_ids_impl(resolved_date)

    def save_txt_snapshot(self, data: NewsData | NormalizedCrawlBatch) -> Optional[str]:
        if not self.enable_txt:
            return None

        if isinstance(data, NormalizedCrawlBatch):
            data = data.to_news_data()

        try:
            date_folder = self._format_date_folder(data.date)
            txt_dir = self.data_dir / "txt" / date_folder
            txt_dir.mkdir(parents=True, exist_ok=True)
            file_path = txt_dir / f"{data.crawl_time}.txt"

            with open(file_path, "w", encoding="utf-8") as f:
                for source_id, news_list in data.items.items():
                    source_name = data.id_to_name.get(source_id, source_id)
                    if source_name and source_name != source_id:
                        f.write(f"{source_id} | {source_name}\n")
                    else:
                        f.write(f"{source_id}\n")

                    sorted_news = sorted(news_list, key=lambda item: item.rank)
                    for item in sorted_news:
                        line = f"{item.rank}. {item.title}"
                        if item.url:
                            line += f" [URL:{item.url}]"
                        if item.mobile_url:
                            line += f" [MOBILE:{item.mobile_url}]"
                        f.write(line + "\n")
                    f.write("\n")

                if data.failed_ids:
                    f.write("==== 以下ID请求失败 ====\n")
                    for failed_id in data.failed_ids:
                        f.write(f"{failed_id}\n")

            print(f"[本地存储] TXT 快照已保存: {file_path}")
            return str(file_path)
        except Exception as e:
            print(f"[本地存储] 保存 TXT 快照失败: {e}")
            return None

    def save_html_report(self, html_content: str, filename: str) -> Optional[str]:
        if not self.enable_html:
            return None

        try:
            date_folder = self._format_date_folder()
            html_dir = self.data_dir / "html" / date_folder
            html_dir.mkdir(parents=True, exist_ok=True)
            file_path = html_dir / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"[本地存储] HTML 报告已保存: {file_path}")
            return str(file_path)
        except Exception as e:
            print(f"[本地存储] 保存 HTML 报告失败: {e}")
            return None

    def cleanup(self) -> None:
        for db_path in list(self._db_connections):
            try:
                self.runtime.close_connection(db_path)
                print(f"[本地存储] 关闭数据库连接: {db_path}")
            except Exception as e:
                print(f"[本地存储] 关闭连接失败 {db_path}: {e}")

    def cleanup_old_data(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0

        deleted_count = 0
        cutoff_date = self._get_configured_time() - timedelta(days=retention_days)

        def parse_date_from_name(name: str) -> Optional[datetime]:
            name = name.replace(".db", "")
            try:
                date_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", name)
                if date_match:
                    return datetime(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                        tzinfo=pytz.timezone(self.timezone),
                    )
            except Exception:
                pass
            return None

        try:
            if not self.data_dir.exists():
                return 0

            db_dir = self.data_dir / "news"
            if db_dir.exists():
                for db_file in db_dir.glob("*.db"):
                    file_date = parse_date_from_name(db_file.name)
                    if file_date and file_date < cutoff_date:
                        db_path = str(db_file)
                        if db_path in self._db_connections:
                            try:
                                self.runtime.close_connection(db_path)
                            except Exception:
                                pass

                        try:
                            db_file.unlink()
                            deleted_count += 1
                            print(f"[本地存储] 清理过期数据: news/{db_file.name}")
                        except Exception as e:
                            print(f"[本地存储] 删除文件失败 {db_file}: {e}")

            for snapshot_type in ["txt", "html"]:
                snapshot_dir = self.data_dir / snapshot_type
                if not snapshot_dir.exists():
                    continue

                for date_folder in snapshot_dir.iterdir():
                    if not date_folder.is_dir() or date_folder.name.startswith("."):
                        continue

                    folder_date = parse_date_from_name(date_folder.name)
                    if folder_date and folder_date < cutoff_date:
                        try:
                            shutil.rmtree(date_folder)
                            deleted_count += 1
                            print(f"[本地存储] 清理过期数据: {snapshot_type}/{date_folder.name}")
                        except Exception as e:
                            print(f"[本地存储] 删除目录失败 {date_folder}: {e}")

            if deleted_count > 0:
                print(f"[本地存储] 共清理 {deleted_count} 个过期文件/目录")
            return deleted_count
        except Exception as e:
            print(f"[本地存储] 清理过期数据失败: {e}")
            return deleted_count

    def __del__(self):
        self.cleanup()
