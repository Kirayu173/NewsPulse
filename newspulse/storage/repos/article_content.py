# coding=utf-8
"""SQLite repository for cached article or equivalent content."""

from __future__ import annotations

import json
from typing import Optional

from newspulse.storage.base import ArticleContentRecord
from newspulse.storage.repos.base import SQLiteRepositoryBase


class ArticleContentRepository(SQLiteRepositoryBase):
    """Persist and load stage-5 article content cache entries."""

    def _get_by_normalized_url_impl(
        self,
        normalized_url: str,
        date: Optional[str] = None,
    ) -> Optional[ArticleContentRecord]:
        normalized_url = str(normalized_url or '').strip()
        if not normalized_url:
            return None

        conn = self._get_connection(date)
        row = conn.execute(
            """
            SELECT normalized_url, source_type, source_id, source_name, source_kind,
                   original_url, final_url, title, excerpt, content_text, content_markdown,
                   content_hash, published_at, author, extractor_name, fetch_status,
                   error_type, error_message, trace_json, fetched_at, updated_at
            FROM article_contents
            WHERE normalized_url = ?
            """,
            (normalized_url,),
        ).fetchone()
        if row is None:
            return None
        return ArticleContentRecord(
            normalized_url=row[0],
            source_type=row[1] or '',
            source_id=row[2] or '',
            source_name=row[3] or '',
            source_kind=row[4] or '',
            original_url=row[5] or '',
            final_url=row[6] or '',
            title=row[7] or '',
            excerpt=row[8] or '',
            content_text=row[9] or '',
            content_markdown=row[10] or '',
            content_hash=row[11] or '',
            published_at=row[12] or '',
            author=row[13] or '',
            extractor_name=row[14] or '',
            fetch_status=row[15] or '',
            error_type=row[16] or '',
            error_message=row[17] or '',
            trace=_deserialize_trace(row[18]),
            fetched_at=row[19] or '',
            updated_at=row[20] or '',
        )

    def _save_impl(self, record: ArticleContentRecord, date: Optional[str] = None) -> bool:
        normalized_url = str(record.normalized_url or '').strip()
        if not normalized_url:
            return False

        conn = self._get_connection(date)
        now_str = self._get_configured_time().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            """
            INSERT INTO article_contents (
                normalized_url, source_type, source_id, source_name, source_kind,
                original_url, final_url, title, excerpt, content_text, content_markdown,
                content_hash, published_at, author, extractor_name, fetch_status,
                error_type, error_message, trace_json, fetched_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_url) DO UPDATE SET
                source_type = excluded.source_type,
                source_id = excluded.source_id,
                source_name = excluded.source_name,
                source_kind = excluded.source_kind,
                original_url = excluded.original_url,
                final_url = excluded.final_url,
                title = excluded.title,
                excerpt = excluded.excerpt,
                content_text = excluded.content_text,
                content_markdown = excluded.content_markdown,
                content_hash = excluded.content_hash,
                published_at = excluded.published_at,
                author = excluded.author,
                extractor_name = excluded.extractor_name,
                fetch_status = excluded.fetch_status,
                error_type = excluded.error_type,
                error_message = excluded.error_message,
                trace_json = excluded.trace_json,
                fetched_at = excluded.fetched_at,
                updated_at = excluded.updated_at
            """,
            (
                normalized_url,
                record.source_type,
                record.source_id,
                record.source_name,
                record.source_kind,
                record.original_url,
                record.final_url,
                record.title,
                record.excerpt,
                record.content_text,
                record.content_markdown,
                record.content_hash,
                record.published_at,
                record.author,
                record.extractor_name,
                record.fetch_status,
                record.error_type,
                record.error_message,
                json.dumps(record.trace or {}, ensure_ascii=False),
                record.fetched_at or now_str,
                now_str,
            ),
        )
        conn.commit()
        return True


def _deserialize_trace(raw: object) -> dict:
    text = str(raw or '').strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}
