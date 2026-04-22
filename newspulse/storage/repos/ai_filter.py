# coding=utf-8
import sqlite3
from typing import Any, Dict, List, Optional

from newspulse.storage.repos.base import SQLiteRepositoryBase
from newspulse.utils.logging import get_logger


logger = get_logger(__name__)


class AIFilterRepository(SQLiteRepositoryBase):
    @staticmethod
    def _normalize_model_key(model_key: Optional[str]) -> str:
        return str(model_key or "").strip()

    def _get_active_tags_impl(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> List[Dict[str, Any]]:
        """获取指定兴趣文件的 active 标签列表"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, tag, description, version, prompt_hash, priority
                FROM ai_filter_tags
                WHERE status = 'active' AND interests_file = ?
                ORDER BY priority ASC, id ASC
            """, (interests_file,))

            return [
                {
                    "id": row[0], "tag": row[1], "description": row[2],
                    "version": row[3], "prompt_hash": row[4], "priority": row[5],
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.exception(f"[AI筛选] 获取标签失败: {e}")
            return []

    def _get_latest_prompt_hash_impl(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> Optional[str]:
        """获取指定兴趣文件最新版本标签的 prompt_hash"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT prompt_hash FROM ai_filter_tags
                WHERE status = 'active' AND interests_file = ?
                ORDER BY version DESC
                LIMIT 1
            """, (interests_file,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.exception(f"[AI筛选] 获取 prompt_hash 失败: {e}")
            return None

    def _get_latest_tag_version_impl(self, date: Optional[str] = None) -> int:
        """获取最新版本号"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT MAX(version) FROM ai_filter_tags
            """)
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception as e:
            logger.exception(f"[AI筛选] 获取版本号失败: {e}")
            return 0

    def _deprecate_all_tags_impl(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> int:
        """将指定兴趣文件的 active 标签和关联的分类结果标记为 deprecated"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")

            # 获取该兴趣文件的 active 标签 id
            cursor.execute(
                "SELECT id FROM ai_filter_tags WHERE status = 'active' AND interests_file = ?",
                (interests_file,)
            )
            tag_ids = [row[0] for row in cursor.fetchall()]

            if not tag_ids:
                return 0

            # 废弃标签
            placeholders = ",".join("?" * len(tag_ids))
            cursor.execute(f"""
                UPDATE ai_filter_tags
                SET status = 'deprecated', deprecated_at = ?
                WHERE id IN ({placeholders})
            """, [now_str] + tag_ids)
            tag_count = cursor.rowcount

            # 废弃关联的分类结果
            placeholders = ",".join("?" * len(tag_ids))
            cursor.execute(f"""
                UPDATE ai_filter_results
                SET status = 'deprecated', deprecated_at = ?
                WHERE tag_id IN ({placeholders}) AND status = 'active'
            """, [now_str] + tag_ids)

            conn.commit()
            logger.exception(f"[AI筛选] 已废弃 {tag_count} 个标签及关联分类结果")
            return tag_count
        except Exception as e:
            logger.exception(f"[AI筛选] 废弃标签失败: {e}")
            return 0

    def _save_tags_impl(
        self, date: Optional[str], tags: List[Dict], version: int, prompt_hash: str,
        interests_file: str = "ai_interests.txt"
    ) -> int:
        """保存新提取的标签"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")

            count = 0
            for idx, tag_data in enumerate(tags, start=1):
                priority = tag_data.get("priority", idx)
                try:
                    priority = int(priority)
                except (TypeError, ValueError):
                    priority = idx
                cursor.execute("""
                    INSERT INTO ai_filter_tags
                    (tag, description, priority, version, prompt_hash, interests_file, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    tag_data["tag"],
                    tag_data.get("description", ""),
                    priority,
                    version,
                    prompt_hash,
                    interests_file,
                    now_str,
                ))
                count += 1

            conn.commit()
            return count
        except Exception as e:
            logger.exception(f"[AI筛选] 保存标签失败: {e}")
            return 0

    def _deprecate_specific_tags_impl(
        self, date: Optional[str], tag_ids: List[int]
    ) -> int:
        """废弃指定 ID 的标签及其关联分类结果（增量更新时使用）"""
        if not tag_ids:
            return 0
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")

            placeholders = ",".join("?" * len(tag_ids))

            cursor.execute(f"""
                UPDATE ai_filter_tags
                SET status = 'deprecated', deprecated_at = ?
                WHERE id IN ({placeholders})
            """, [now_str] + tag_ids)
            tag_count = cursor.rowcount

            cursor.execute(f"""
                UPDATE ai_filter_results
                SET status = 'deprecated', deprecated_at = ?
                WHERE tag_id IN ({placeholders}) AND status = 'active'
            """, [now_str] + tag_ids)

            conn.commit()
            return tag_count
        except Exception as e:
            logger.exception(f"[AI筛选] 废弃指定标签失败: {e}")
            return 0

    def _update_tags_hash_impl(
        self, date: Optional[str], interests_file: str, new_hash: str
    ) -> int:
        """更新指定兴趣文件所有 active 标签的 prompt_hash（增量更新时使用）"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE ai_filter_tags
                SET prompt_hash = ?
                WHERE interests_file = ? AND status = 'active'
            """, (new_hash, interests_file))
            count = cursor.rowcount

            conn.commit()
            return count
        except Exception as e:
            logger.exception(f"[AI筛选] 更新标签 hash 失败: {e}")
            return 0

    def _update_tag_descriptions_impl(
        self, date: Optional[str], tag_updates: List[Dict],
        interests_file: str = "ai_interests.txt"
    ) -> int:
        """按 tag 名匹配，更新 active 标签的 description 字段"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            count = 0
            for t in tag_updates:
                tag_name = t.get("tag", "")
                description = t.get("description", "")
                if not tag_name:
                    continue
                cursor.execute("""
                    UPDATE ai_filter_tags
                    SET description = ?
                    WHERE tag = ? AND interests_file = ? AND status = 'active'
                """, (description, tag_name, interests_file))
                count += cursor.rowcount

            conn.commit()
            return count
        except Exception as e:
            logger.exception(f"[AI筛选] 更新标签描述失败: {e}")
            return 0

    def _update_tag_priorities_impl(
        self, date: Optional[str], tag_priorities: List[Dict],
        interests_file: str = "ai_interests.txt"
    ) -> int:
        """按 tag 名匹配，更新 active 标签的 priority 字段"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            count = 0
            for t in tag_priorities:
                tag_name = t.get("tag", "")
                priority = t.get("priority")
                if not tag_name:
                    continue
                try:
                    priority = int(priority)
                except (TypeError, ValueError):
                    continue
                cursor.execute("""
                    UPDATE ai_filter_tags
                    SET priority = ?
                    WHERE tag = ? AND interests_file = ? AND status = 'active'
                """, (priority, tag_name, interests_file))
                count += cursor.rowcount

            conn.commit()
            return count
        except Exception as e:
            logger.exception(f"[AI筛选] 更新标签优先级失败: {e}")
            return 0

    def _save_analyzed_news_impl(
        self,
        date: Optional[str],
        news_ids: List[int],
        source_type: str,
        interests_file: str,
        prompt_hash: str,
        matched_ids: set,
        tag_version: int = 0,
        model_key: str = "",
    ) -> int:
        """Persist analyzed-news cache entries for the current classification scope."""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")
            normalized_prompt_hash = str(prompt_hash or "").strip()
            normalized_tag_version = int(tag_version or 0)
            normalized_model_key = self._normalize_model_key(model_key)

            count = 0
            for nid in news_ids:
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO ai_filter_analyzed_news (
                            news_item_id,
                            source_type,
                            interests_file,
                            prompt_hash,
                            tag_version,
                            model_key,
                            matched,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            nid,
                            source_type,
                            interests_file,
                            normalized_prompt_hash,
                            normalized_tag_version,
                            normalized_model_key,
                            1 if nid in matched_ids else 0,
                            now_str,
                        ),
                    )
                    count += 1
                except Exception:
                    pass

            conn.commit()
            return count
        except Exception as e:
            logger.exception("[AI filter] Failed to save analyzed-news cache: %s", e)
            return 0

    def _get_analyzed_news_ids_impl(
        self,
        date: Optional[str] = None,
        source_type: str = "hotlist",
        interests_file: str = "ai_interests.txt",
        prompt_hash: Optional[str] = None,
        tag_version: Optional[int] = None,
        model_key: Optional[str] = None,
    ) -> set:
        """Return analyzed news ids for the requested cache scope."""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            clauses = ["source_type = ?", "interests_file = ?"]
            params: List[Any] = [source_type, interests_file]
            if prompt_hash is not None:
                clauses.append("prompt_hash = ?")
                params.append(str(prompt_hash or "").strip())
            if tag_version is not None:
                clauses.append("tag_version = ?")
                params.append(int(tag_version or 0))
            if model_key is not None:
                clauses.append("model_key = ?")
                params.append(self._normalize_model_key(model_key))

            cursor.execute(
                f"""
                SELECT DISTINCT news_item_id FROM ai_filter_analyzed_news
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logger.exception("[AI filter] Failed to load analyzed-news ids: %s", e)
            return set()

    def _get_cached_classification_impl(
        self,
        news_item_id: int,
        date: Optional[str] = None,
        *,
        source_type: str = "hotlist",
        interests_file: str = "ai_interests.txt",
        prompt_hash: str = "",
        tag_version: int = 0,
        model_key: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Return cached classification metadata for one news item."""
        results = self._get_cached_classifications_impl(
            [news_item_id],
            date=date,
            source_type=source_type,
            interests_file=interests_file,
            prompt_hash=prompt_hash,
            tag_version=tag_version,
            model_key=model_key,
        )
        return results.get(int(news_item_id))

    def _get_cached_classifications_impl(
        self,
        news_item_ids: List[int],
        date: Optional[str] = None,
        *,
        source_type: str = "hotlist",
        interests_file: str = "ai_interests.txt",
        prompt_hash: str = "",
        tag_version: int = 0,
        model_key: str = "",
    ) -> Dict[int, Dict[str, Any]]:
        """Return cached classification metadata for multiple news items."""
        normalized_ids: List[int] = []
        for news_item_id in news_item_ids:
            try:
                normalized_ids.append(int(news_item_id))
            except (TypeError, ValueError):
                continue
        if not normalized_ids:
            return {}

        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(normalized_ids))
            cursor.execute(
                f"""
                SELECT
                    news_item_id,
                    source_type,
                    interests_file,
                    prompt_hash,
                    tag_version,
                    model_key,
                    matched,
                    created_at
                FROM ai_filter_analyzed_news
                WHERE news_item_id IN ({placeholders})
                    AND source_type = ?
                    AND interests_file = ?
                    AND prompt_hash = ?
                    AND tag_version = ?
                    AND model_key = ?
                """,
                [
                    *normalized_ids,
                    source_type,
                    interests_file,
                    str(prompt_hash or "").strip(),
                    int(tag_version or 0),
                    self._normalize_model_key(model_key),
                ],
            )
            return {
                int(row[0]): {
                    "news_item_id": int(row[0]),
                    "source_type": row[1],
                    "interests_file": row[2],
                    "prompt_hash": row[3],
                    "tag_version": int(row[4] or 0),
                    "model_key": row[5] or "",
                    "matched": bool(row[6]),
                    "created_at": row[7],
                }
                for row in cursor.fetchall()
            }
        except Exception as e:
            logger.exception("[AI filter] Failed to load cached classifications: %s", e)
            return {}

    def _clear_analyzed_news_impl(
        self,
        date: Optional[str] = None,
        interests_file: str = "ai_interests.txt",
        prompt_hash: Optional[str] = None,
        tag_version: Optional[int] = None,
        model_key: Optional[str] = None,
    ) -> int:
        """Clear analyzed-news cache rows for the requested scope."""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            clauses = ["interests_file = ?"]
            params: List[Any] = [interests_file]
            if prompt_hash is not None:
                clauses.append("prompt_hash = ?")
                params.append(str(prompt_hash or "").strip())
            if tag_version is not None:
                clauses.append("tag_version = ?")
                params.append(int(tag_version or 0))
            if model_key is not None:
                clauses.append("model_key = ?")
                params.append(self._normalize_model_key(model_key))

            cursor.execute(
                f"""
                DELETE FROM ai_filter_analyzed_news
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception as e:
            logger.exception("[AI filter] Failed to clear analyzed-news cache: %s", e)
            return 0

    def _clear_unmatched_analyzed_news_impl(
        self,
        date: Optional[str] = None,
        interests_file: str = "ai_interests.txt",
        prompt_hash: Optional[str] = None,
        tag_version: Optional[int] = None,
        model_key: Optional[str] = None,
    ) -> int:
        """Clear unmatched analyzed-news cache rows for the requested scope."""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            clauses = ["interests_file = ?", "matched = 0"]
            params: List[Any] = [interests_file]
            if prompt_hash is not None:
                clauses.append("prompt_hash = ?")
                params.append(str(prompt_hash or "").strip())
            if tag_version is not None:
                clauses.append("tag_version = ?")
                params.append(int(tag_version or 0))
            if model_key is not None:
                clauses.append("model_key = ?")
                params.append(self._normalize_model_key(model_key))

            cursor.execute(
                f"""
                DELETE FROM ai_filter_analyzed_news
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception as e:
            logger.exception("[AI filter] Failed to clear unmatched analyzed-news cache: %s", e)
            return 0

    def _save_filter_results_impl(
        self, date: Optional[str], results: List[Dict]
    ) -> int:
        """批量保存分类结果"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()
            now_str = self._get_configured_time().strftime("%Y-%m-%d %H:%M:%S")

            count = 0
            for r in results:
                try:
                    cursor.execute("""
                        INSERT INTO ai_filter_results
                        (news_item_id, source_type, tag_id, relevance_score, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        r["news_item_id"],
                        r.get("source_type", "hotlist"),
                        r["tag_id"],
                        r.get("relevance_score", 0.0),
                        now_str,
                    ))
                    count += 1
                except sqlite3.IntegrityError:
                    pass  # 重复记录，跳过

            conn.commit()
            return count
        except Exception as e:
            logger.exception(f"[AI筛选] 保存分类结果失败: {e}")
            return 0

    def _get_active_filter_results_impl(self, date: Optional[str] = None, interests_file: str = "ai_interests.txt") -> List[Dict[str, Any]]:
        """获取指定兴趣文件的 active 分类结果，JOIN news_items 获取新闻详情"""
        try:
            conn = self._get_connection(date)
            cursor = conn.cursor()

            # 热榜结果
            cursor.execute("""
                SELECT
                    r.news_item_id, r.source_type, r.tag_id, r.relevance_score,
                    t.tag, t.description as tag_description, t.priority,
                    n.title, n.platform_id as source_id, p.name as source_name,
                    n.url, n.mobile_url, n.rank,
                    n.first_crawl_time, n.last_crawl_time, n.crawl_count
                FROM ai_filter_results r
                JOIN ai_filter_tags t ON r.tag_id = t.id
                JOIN news_items n ON r.news_item_id = n.id
                LEFT JOIN platforms p ON n.platform_id = p.id
                WHERE r.status = 'active' AND r.source_type = 'hotlist'
                    AND t.status = 'active' AND t.interests_file = ?
                ORDER BY t.priority ASC, t.id ASC, r.relevance_score DESC
            """, (interests_file,))

            results = []
            hotlist_news_ids = []
            for row in cursor.fetchall():
                results.append({
                    "news_item_id": row[0], "source_type": row[1],
                    "tag_id": row[2], "relevance_score": row[3],
                    "tag": row[4], "tag_description": row[5], "tag_priority": row[6],
                    "title": row[7], "source_id": row[8],
                    "source_name": row[9] or row[8],
                    "url": row[10] or "", "mobile_url": row[11] or "",
                    "rank": row[12],
                    "first_time": row[13], "last_time": row[14],
                    "count": row[15],
                })
                hotlist_news_ids.append(row[0])

            # 批量查排名历史（热榜）
            ranks_map: Dict[int, List[int]] = {}
            if hotlist_news_ids:
                unique_ids = list(set(hotlist_news_ids))
                placeholders = ",".join("?" * len(unique_ids))
                cursor.execute(f"""
                    SELECT news_item_id, rank FROM rank_history
                    WHERE news_item_id IN ({placeholders}) AND rank != 0
                """, unique_ids)
                for rh_row in cursor.fetchall():
                    nid, rank = rh_row[0], rh_row[1]
                    if nid not in ranks_map:
                        ranks_map[nid] = []
                    if rank not in ranks_map[nid]:
                        ranks_map[nid].append(rank)

            for item in results:
                item["ranks"] = ranks_map.get(item["news_item_id"], [item["rank"]])


            return results
        except Exception as e:
            logger.exception(f"[AI筛选] 获取分类结果失败: {e}")
            return []

