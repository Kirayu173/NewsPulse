# coding=utf-8
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from newspulse.storage.base import (
    NewsData,
    NewsItem,
    NormalizedCrawlBatch,
    SourceFailureRecord,
    convert_news_data_to_normalized_batch,
)
from newspulse.storage.repos.base import SQLiteRepositoryBase
from newspulse.utils.logging import get_logger
from newspulse.utils.url import normalize_url


logger = get_logger(__name__)


@dataclass
class _PreparedNewsItem:
    source_id: str
    title: str
    rank: int
    url: str
    mobile_url: str
    summary: str
    metadata: Dict[str, Any]


class NewsRepository(SQLiteRepositoryBase):
    def _save_news_data_impl(self, data: NewsData, log_prefix: str = "[存储]") -> tuple[bool, int, int, int, int]:
        return self._save_normalized_crawl_batch_impl(
            convert_news_data_to_normalized_batch(data),
            log_prefix=log_prefix,
        )

    def _sync_platform(self, cursor: sqlite3.Cursor, source_id: str, source_name: str, now_str: str) -> None:
        cursor.execute(
            """
            INSERT INTO platforms (id, name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (source_id, source_name or source_id, now_str),
        )

    def _load_failure_records(
        self,
        cursor: sqlite3.Cursor,
        *,
        latest_time: Optional[str] = None,
    ) -> list[SourceFailureRecord]:
        if latest_time:
            cursor.execute(
                """
                SELECT css.platform_id, p.name, COALESCE(csf.resolved_source_id, css.platform_id),
                       COALESCE(csf.exception_type, ''), COALESCE(csf.message, ''),
                       COALESCE(csf.attempts, 1), COALESCE(csf.retryable, 1)
                FROM crawl_source_status css
                JOIN crawl_records cr ON css.crawl_record_id = cr.id
                LEFT JOIN platforms p ON css.platform_id = p.id
                LEFT JOIN crawl_source_failures csf
                  ON csf.crawl_record_id = css.crawl_record_id
                 AND csf.platform_id = css.platform_id
                WHERE cr.crawl_time = ? AND css.status = 'failed'
                ORDER BY css.platform_id
                """,
                (latest_time,),
            )
        else:
            cursor.execute(
                """
                SELECT css.platform_id, p.name, COALESCE(csf.resolved_source_id, css.platform_id),
                       COALESCE(csf.exception_type, ''), COALESCE(csf.message, ''),
                       COALESCE(csf.attempts, 1), COALESCE(csf.retryable, 1)
                FROM crawl_source_status css
                JOIN crawl_records cr ON css.crawl_record_id = cr.id
                LEFT JOIN platforms p ON css.platform_id = p.id
                LEFT JOIN crawl_source_failures csf
                  ON csf.crawl_record_id = css.crawl_record_id
                 AND csf.platform_id = css.platform_id
                WHERE css.status = 'failed'
                  AND cr.crawl_time = (
                      SELECT MAX(cr2.crawl_time)
                      FROM crawl_source_status css2
                      JOIN crawl_records cr2 ON css2.crawl_record_id = cr2.id
                      WHERE css2.platform_id = css.platform_id
                        AND css2.status = 'failed'
                  )
                ORDER BY cr.crawl_time DESC, css.platform_id
                """,
            )

        failures: list[SourceFailureRecord] = []
        seen_source_ids: set[str] = set()
        for row in cursor.fetchall():
            source_id = row[0]
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            failures.append(
                SourceFailureRecord(
                    source_id=source_id,
                    source_name=row[1] or source_id,
                    resolved_source_id=row[2] or source_id,
                    exception_type=row[3] or "",
                    message=row[4] or "",
                    attempts=int(row[5] or 1),
                    retryable=bool(row[6]),
                )
            )
        return failures

    def _build_rank_maps(
        self,
        cursor: sqlite3.Cursor,
        news_ids: list[int],
    ) -> tuple[Dict[int, List[int]], Dict[int, List[Dict[str, Any]]]]:
        rank_history_map: Dict[int, List[int]] = {}
        rank_timeline_map: Dict[int, List[Dict[str, Any]]] = {}
        if not news_ids:
            return rank_history_map, rank_timeline_map

        placeholders = ",".join("?" * len(news_ids))
        cursor.execute(
            f"""
            SELECT rh.news_item_id, rh.rank, rh.crawl_time
            FROM rank_history rh
            JOIN news_items ni ON rh.news_item_id = ni.id
            WHERE rh.news_item_id IN ({placeholders})
              AND NOT (rh.rank = 0 AND rh.crawl_time > ni.last_crawl_time)
            ORDER BY rh.news_item_id, rh.crawl_time
            """,
            news_ids,
        )
        for rh_row in cursor.fetchall():
            news_id, rank, crawl_time = rh_row[0], rh_row[1], rh_row[2]

            if news_id not in rank_history_map:
                rank_history_map[news_id] = []
            if rank != 0 and rank not in rank_history_map[news_id]:
                rank_history_map[news_id].append(rank)

            if news_id not in rank_timeline_map:
                rank_timeline_map[news_id] = []
            time_part = crawl_time.split()[1][:5] if " " in crawl_time else crawl_time[:5]
            rank_timeline_map[news_id].append(
                {
                    "time": time_part,
                    "rank": rank if rank != 0 else None,
                }
            )

        return rank_history_map, rank_timeline_map

    def _rows_to_news_data(
        self,
        cursor: sqlite3.Cursor,
        rows: list[sqlite3.Row],
        *,
        crawl_date: str,
        crawl_time: str,
        failures: list[SourceFailureRecord],
    ) -> NewsData:
        items: Dict[str, List[NewsItem]] = {}
        id_to_name: Dict[str, str] = {}
        news_ids = [row[0] for row in rows]
        rank_history_map, rank_timeline_map = self._build_rank_maps(cursor, news_ids)

        for row in rows:
            news_id = row[0]
            platform_id = row[2]
            platform_name = row[3] or platform_id
            id_to_name[platform_id] = platform_name
            items.setdefault(platform_id, []).append(
                NewsItem(
                    title=row[1],
                    source_id=platform_id,
                    source_name=platform_name,
                    rank=row[4],
                    url=row[5] or "",
                    mobile_url=row[6] or "",
                    summary=row[7] or "",
                    metadata=_deserialize_source_metadata(row[8]),
                    crawl_time=row[10],
                    ranks=rank_history_map.get(news_id, [row[4]]),
                    first_time=row[9],
                    last_time=row[10],
                    count=row[11],
                    rank_timeline=rank_timeline_map.get(news_id, []),
                )
            )

        for failure in failures:
            id_to_name.setdefault(failure.source_id, failure.source_name or failure.source_id)

        return NewsData(
            date=crawl_date,
            crawl_time=crawl_time,
            items=items,
            id_to_name=id_to_name,
            failed_ids=[failure.source_id for failure in failures],
            failures=failures,
        )

    def _save_normalized_crawl_batch_impl(
        self,
        batch: NormalizedCrawlBatch,
        log_prefix: str = "[??]",
    ) -> tuple[bool, int, int, int, int]:
        """
        ???????????? SQLite??????

        Args:
            batch: ?????
            log_prefix: ????

        Returns:
            (success, new_count, updated_count, title_changed_count, off_list_count)
        """
        try:
            conn = self._get_connection(batch.date)
            cursor = conn.cursor()

            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")

            for source in batch.sources:
                self._sync_platform(cursor, source.source_id, source.source_name, now_str)
            for failure in batch.failures:
                self._sync_platform(cursor, failure.source_id, failure.source_name, now_str)

            new_count = 0
            updated_count = 0
            title_changed_count = 0
            success_sources: list[str] = []
            current_urls_by_source: dict[str, set[str]] = {}
            prepared_url_items: dict[tuple[str, str], _PreparedNewsItem] = {}
            prepared_no_url_items: list[_PreparedNewsItem] = []

            for source in batch.sources:
                source_id = source.source_id
                success_sources.append(source_id)
                source_urls = current_urls_by_source.setdefault(source_id, set())

                for item in source.items:
                    normalized_url = normalize_url(item.url, source_id) if item.url else ""
                    prepared_item = _PreparedNewsItem(
                        source_id=source_id,
                        title=item.title,
                        rank=item.rank,
                        url=normalized_url,
                        mobile_url=item.mobile_url,
                        summary=item.summary,
                        metadata=dict(item.metadata or {}),
                    )
                    if normalized_url:
                        source_urls.add(normalized_url)
                        prepared_url_items[(source_id, normalized_url)] = prepared_item
                    else:
                        prepared_no_url_items.append(prepared_item)

            existing_by_key = self._load_existing_news_items(cursor, set(prepared_url_items))

            update_rows: list[tuple[Any, ...]] = []
            insert_rows: list[tuple[Any, ...]] = []
            title_change_rows: list[tuple[Any, ...]] = []
            rank_history_rows: list[tuple[Any, ...]] = []

            for key, item in prepared_url_items.items():
                existing = existing_by_key.get(key)
                if existing is None:
                    insert_rows.append(
                        (
                            item.title,
                            item.source_id,
                            item.rank,
                            item.url,
                            item.mobile_url,
                            item.summary,
                            _serialize_source_metadata(item.metadata),
                            batch.crawl_time,
                            batch.crawl_time,
                            now_str,
                            now_str,
                        )
                    )
                    continue

                existing_id = int(existing["id"])
                existing_title = str(existing["title"] or "")
                merged_summary = item.summary or str(existing["summary"] or "")
                merged_metadata = _merge_source_metadata(
                    _deserialize_source_metadata(existing["source_metadata_json"]),
                    item.metadata,
                )
                if existing_title != item.title:
                    title_change_rows.append((existing_id, existing_title, item.title, now_str))

                update_rows.append(
                    (
                        item.title,
                        item.rank,
                        item.mobile_url,
                        merged_summary,
                        _serialize_source_metadata(merged_metadata),
                        batch.crawl_time,
                        now_str,
                        existing_id,
                    )
                )
                rank_history_rows.append((existing_id, item.rank, batch.crawl_time, now_str))

            if update_rows:
                cursor.executemany(
                    """
                    UPDATE news_items SET
                        title = ?,
                        rank = ?,
                        mobile_url = ?,
                        summary = ?,
                        source_metadata_json = ?,
                        last_crawl_time = ?,
                        crawl_count = crawl_count + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    update_rows,
                )
                updated_count = len(update_rows)

            if title_change_rows:
                cursor.executemany(
                    """
                    INSERT INTO title_changes
                    (news_item_id, old_title, new_title, changed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    title_change_rows,
                )
                title_changed_count = len(title_change_rows)

            inserted_items = self._bulk_insert_news_items(cursor, insert_rows)
            new_count += len(inserted_items)
            rank_history_rows.extend(
                (news_id, rank, batch.crawl_time, now_str)
                for news_id, rank in inserted_items
            )

            no_url_insert_rows = [
                (
                    item.title,
                    item.source_id,
                    item.rank,
                    "",
                    item.mobile_url,
                    item.summary,
                    _serialize_source_metadata(item.metadata),
                    batch.crawl_time,
                    batch.crawl_time,
                    now_str,
                    now_str,
                )
                for item in prepared_no_url_items
            ]
            no_url_inserted_items = self._bulk_insert_news_items(cursor, no_url_insert_rows)
            new_count += len(no_url_inserted_items)
            rank_history_rows.extend(
                (news_id, rank, batch.crawl_time, now_str)
                for news_id, rank in no_url_inserted_items
            )

            total_items = new_count + updated_count

            off_list_count = 0

            cursor.execute(
                """
                SELECT crawl_time FROM crawl_records
                WHERE crawl_time < ?
                ORDER BY crawl_time DESC
                LIMIT 1
                """,
                (batch.crawl_time,),
            )
            prev_record = cursor.fetchone()

            if prev_record:
                prev_crawl_time = prev_record[0]
                previous_rows = self._load_previous_source_rows(cursor, prev_crawl_time, success_sources)
                for news_id, source_id, url in previous_rows:
                    if not url or url in current_urls_by_source.get(source_id, set()):
                        continue
                    rank_history_rows.append((news_id, 0, batch.crawl_time, now_str))
                    off_list_count += 1

            if rank_history_rows:
                cursor.executemany(
                    """
                    INSERT INTO rank_history
                    (news_item_id, rank, crawl_time, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    rank_history_rows,
                )

            cursor.execute(
                """
                INSERT OR REPLACE INTO crawl_records
                (crawl_time, total_items, created_at)
                VALUES (?, ?, ?)
                """,
                (batch.crawl_time, total_items, now_str),
            )

            cursor.execute(
                """
                SELECT id FROM crawl_records WHERE crawl_time = ?
                """,
                (batch.crawl_time,),
            )
            record_row = cursor.fetchone()
            if record_row:
                crawl_record_id = record_row[0]

                status_rows = [(crawl_record_id, source_id, "success") for source_id in success_sources]
                status_rows.extend((crawl_record_id, failure.source_id, "failed") for failure in batch.failures)
                if status_rows:
                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO crawl_source_status
                        (crawl_record_id, platform_id, status)
                        VALUES (?, ?, ?)
                        """,
                        status_rows,
                    )

                failure_rows = [
                    (
                        crawl_record_id,
                        failure.source_id,
                        failure.resolved_source_id or failure.source_id,
                        failure.exception_type,
                        failure.message,
                        failure.attempts,
                        1 if failure.retryable else 0,
                        now_str,
                    )
                    for failure in batch.failures
                ]
                if failure_rows:
                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO crawl_source_failures
                        (crawl_record_id, platform_id, resolved_source_id, exception_type,
                         message, attempts, retryable, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        failure_rows,
                    )

            conn.commit()

            return True, new_count, updated_count, title_changed_count, off_list_count

        except Exception:
            logger.exception("%s ????", log_prefix)
            return False, 0, 0, 0, 0
    def _load_existing_news_items(
        self,
        cursor: sqlite3.Cursor,
        source_url_pairs: set[tuple[str, str]],
    ) -> dict[tuple[str, str], sqlite3.Row]:
        if not source_url_pairs:
            return {}

        grouped_urls: dict[str, list[str]] = {}
        for source_id, normalized_url in sorted(source_url_pairs):
            grouped_urls.setdefault(source_id, []).append(normalized_url)

        rows: dict[tuple[str, str], sqlite3.Row] = {}
        for source_id, urls in grouped_urls.items():
            for chunk in _chunked(urls, 200):
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(
                    f"""
                    SELECT id, title, summary, source_metadata_json, url, platform_id
                    FROM news_items
                    WHERE platform_id = ? AND url IN ({placeholders})
                    """,
                    [source_id, *chunk],
                )
                for row in cursor.fetchall():
                    rows[(str(row["platform_id"]), str(row["url"]))] = row
        return rows

    def _load_previous_source_rows(
        self,
        cursor: sqlite3.Cursor,
        crawl_time: str,
        source_ids: list[str],
    ) -> list[tuple[int, str, str]]:
        if not source_ids:
            return []

        rows: list[tuple[int, str, str]] = []
        for chunk in _chunked(source_ids, 200):
            placeholders = ",".join("?" for _ in chunk)
            cursor.execute(
                f"""
                SELECT id, platform_id, url
                FROM news_items
                WHERE last_crawl_time = ?
                  AND url != ''
                  AND platform_id IN ({placeholders})
                """,
                [crawl_time, *chunk],
            )
            rows.extend((int(row["id"]), str(row["platform_id"]), str(row["url"])) for row in cursor.fetchall())
        return rows

    def _bulk_insert_news_items(
        self,
        cursor: sqlite3.Cursor,
        rows: list[tuple[Any, ...]],
        *,
        batch_size: int = 80,
    ) -> list[tuple[int, int]]:
        if not rows:
            return []

        inserted: list[tuple[int, int]] = []
        for chunk in _chunked(rows, batch_size):
            placeholders = ",".join("(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)" for _ in chunk)
            params: list[Any] = []
            for row in chunk:
                params.extend(row)
            cursor.execute(
                f"""
                INSERT INTO news_items
                (title, platform_id, rank, url, mobile_url, summary,
                 source_metadata_json,
                 first_crawl_time, last_crawl_time, crawl_count,
                 created_at, updated_at)
                VALUES {placeholders}
                RETURNING id, rank
                """,
                params,
            )
            inserted.extend((int(row["id"]), int(row["rank"])) for row in cursor.fetchall())
        return inserted

    def _get_today_all_data_impl(self, date: Optional[str] = None) -> Optional[NewsData]:
        """
        获取指定日期的所有新闻数据（合并后）

        Args:
            date: 日期字符串，默认为今天

        Returns:
            合并后的新闻数据
        """
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT n.id, n.title, n.platform_id, p.name as platform_name,
                       n.rank, n.url, n.mobile_url, n.summary, n.source_metadata_json,
                       n.first_crawl_time, n.last_crawl_time, n.crawl_count
                FROM news_items n
                LEFT JOIN platforms p ON n.platform_id = p.id
                ORDER BY n.platform_id, n.last_crawl_time
            """)

            rows = cursor.fetchall()

            crawl_date = self._format_date_folder(date)
            cursor.execute("""
                SELECT crawl_time FROM crawl_records
                ORDER BY crawl_time DESC
                LIMIT 1
            """)

            time_row = cursor.fetchone()
            crawl_time = time_row[0] if time_row else self._format_time_filename()
            failures = self._load_failure_records(cursor)
            if not rows:
                if not failures:
                    return None
                return NewsData(
                    date=crawl_date,
                    crawl_time=crawl_time,
                    items={},
                    id_to_name={failure.source_id: failure.source_name or failure.source_id for failure in failures},
                    failed_ids=[failure.source_id for failure in failures],
                    failures=failures,
                )
            return self._rows_to_news_data(
                cursor,
                rows,
                crawl_date=crawl_date,
                crawl_time=crawl_time,
                failures=failures,
            )

        except Exception as e:
            logger.exception(f"[存储] 读取数据失败: {e}")
            return None

    def _get_latest_crawl_data_impl(self, date: Optional[str] = None) -> Optional[NewsData]:
        """
        获取最新一次抓取的数据

        Args:
            date: 日期字符串，默认为今天

        Returns:
            最新抓取的新闻数据
        """
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT crawl_time FROM crawl_records
                ORDER BY crawl_time DESC
                LIMIT 1
            """)

            time_row = cursor.fetchone()
            if not time_row:
                return None

            latest_time = time_row[0]

            cursor.execute("""
                SELECT n.id, n.title, n.platform_id, p.name as platform_name,
                       n.rank, n.url, n.mobile_url, n.summary, n.source_metadata_json,
                       n.first_crawl_time, n.last_crawl_time, n.crawl_count
                FROM news_items n
                LEFT JOIN platforms p ON n.platform_id = p.id
                WHERE n.last_crawl_time = ?
            """, (latest_time,))

            rows = cursor.fetchall()

            crawl_date = self._format_date_folder(date)
            failures = self._load_failure_records(cursor, latest_time=latest_time)
            if not rows:
                if not failures:
                    return None
                return NewsData(
                    date=crawl_date,
                    crawl_time=latest_time,
                    items={},
                    id_to_name={failure.source_id: failure.source_name or failure.source_id for failure in failures},
                    failed_ids=[failure.source_id for failure in failures],
                    failures=failures,
                )
            return self._rows_to_news_data(
                cursor,
                rows,
                crawl_date=crawl_date,
                crawl_time=latest_time,
                failures=failures,
            )

        except Exception as e:
            logger.exception(f"[存储] 获取最新数据失败: {e}")
            return None

    def _detect_new_titles_impl(self, current_data: NewsData) -> Dict[str, Dict]:
        """
        检测新增的标题

        该方法比较当前抓取数据与历史数据，找出新增的标题。
        关键逻辑：只有在历史批次中从未出现过的标题才算新增。

        Args:
            current_data: 当前抓取的数据

        Returns:
            新增的标题数据 {source_id: {title: NewsItem}}
        """
        try:
            # 获取历史数据
            historical_data = self._get_today_all_data_impl(current_data.date)

            if not historical_data:
                # 没有历史数据，所有都是新的
                new_titles = {}
                for source_id, news_list in current_data.items.items():
                    new_titles[source_id] = {item.title: item for item in news_list}
                return new_titles

            # 获取当前批次时间
            current_time = current_data.crawl_time

            # 收集历史标题（first_time < current_time 的标题）
            # 这样可以正确处理同一标题因 URL 变化而产生多条记录的情况
            historical_titles: Dict[str, set] = {}
            for source_id, news_list in historical_data.items.items():
                historical_titles[source_id] = set()
                for item in news_list:
                    first_time = item.first_time or item.crawl_time
                    if first_time < current_time:
                        historical_titles[source_id].add(item.title)

            # 检查是否有历史数据
            has_historical_data = any(len(titles) > 0 for titles in historical_titles.values())
            if not has_historical_data:
                # 第一次抓取，没有"新增"概念
                return {}

            # 检测新增
            new_titles = {}
            for source_id, news_list in current_data.items.items():
                hist_set = historical_titles.get(source_id, set())
                for item in news_list:
                    if item.title not in hist_set:
                        if source_id not in new_titles:
                            new_titles[source_id] = {}
                        new_titles[source_id][item.title] = item

            return new_titles

        except Exception as e:
            logger.exception(f"[存储] 检测新标题失败: {e}")
            return {}

    def _is_first_crawl_today_impl(self, date: Optional[str] = None) -> bool:
        """
        检查是否是当天第一次抓取

        Args:
            date: 日期字符串，默认为今天

        Returns:
            是否是第一次抓取
        """
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) as count FROM crawl_records
            """)

            row = cursor.fetchone()
            count = row[0] if row else 0

            # 如果只有一条或没有记录，视为第一次抓取
            return count <= 1

        except Exception as e:
            logger.exception(f"[存储] 检查首次抓取失败: {e}")
            return True

    def _get_crawl_times_impl(self, date: Optional[str] = None) -> List[str]:
        """
        获取指定日期的所有抓取时间列表

        Args:
            date: 日期字符串，默认为今天

        Returns:
            抓取时间列表（按时间排序）
        """
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT crawl_time FROM crawl_records
                ORDER BY crawl_time
            """)

            rows = cursor.fetchall()
            return [row[0] for row in rows]

        except Exception as e:
            logger.exception(f"[存储] 获取抓取时间列表失败: {e}")
            return []

    def _get_all_news_ids_impl(self, date: Optional[str] = None) -> List[Dict]:
        """获取当日所有新闻的 id 和标题（用于 AI 筛选分类）"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT n.id, n.title, n.platform_id, p.name as platform_name
                FROM news_items n
                LEFT JOIN platforms p ON n.platform_id = p.id
                ORDER BY n.id
            """)

            return [
                {
                    "id": row[0], "title": row[1],
                    "source_id": row[2], "source_name": row[3] or row[2],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.exception(f"[AI筛选] 获取新闻列表失败: {e}")
            return []


def _serialize_source_metadata(metadata: Dict[str, Any] | None) -> str:
    if not metadata:
        return "{}"
    try:
        return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return "{}"


def _deserialize_source_metadata(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    text = str(raw_value or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(data) if isinstance(data, dict) else {}


def _merge_source_metadata(
    existing: Dict[str, Any] | None,
    incoming: Dict[str, Any] | None,
) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(incoming or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged.get(key) or {})
            nested.update(value)
            merged[key] = nested
            continue
        merged[key] = value
    return merged


def _chunked(values: List[Any], size: int) -> List[List[Any]]:
    return [values[index:index + size] for index in range(0, len(values), size)]
