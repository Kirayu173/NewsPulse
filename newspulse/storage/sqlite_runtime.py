# coding=utf-8
"""Shared SQLite runtime for local storage repositories."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from newspulse.utils.time import DEFAULT_TIMEZONE, format_date_folder, format_time_filename, get_configured_time


class SQLiteRuntime:
    """Manage shared SQLite paths, schemas, and connection caches."""

    def __init__(self, data_dir: str = "output", timezone: str = DEFAULT_TIMEZONE):
        self.data_dir = Path(data_dir)
        self.timezone = timezone
        self.db_connections: Dict[str, sqlite3.Connection] = {}

    def get_configured_time(self) -> datetime:
        return get_configured_time(self.timezone)

    def format_date_folder(self, date: Optional[str] = None) -> str:
        return format_date_folder(date, self.timezone)

    def format_time_filename(self) -> str:
        return format_time_filename(self.timezone)

    def get_db_path(self, date: Optional[str] = None, db_type: str = "news") -> Path:
        date_str = self.format_date_folder(date)
        db_dir = self.data_dir / db_type
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / f"{date_str}.db"

    def get_connection(self, date: Optional[str] = None, db_type: str = "news") -> sqlite3.Connection:
        db_path = str(self.get_db_path(date, db_type))
        if db_path not in self.db_connections:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            self.configure_connection(conn)
            self.init_tables(conn, db_type)
            self.db_connections[db_path] = conn
        return self.db_connections[db_path]

    def get_schema_path(self, db_type: str = "news") -> Path:
        return Path(__file__).parent / "schema.sql"

    def get_ai_filter_schema_path(self) -> Path:
        return Path(__file__).parent / "ai_filter_schema.sql"

    def configure_connection(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

    def init_tables(self, conn: sqlite3.Connection, db_type: str = "news") -> None:
        schema_path = self.get_schema_path(db_type)
        if schema_path.exists():
            conn.executescript(schema_path.read_text(encoding="utf-8"))

        if db_type == "news":
            self._ensure_news_schema_columns(conn)
            ai_filter_schema = self.get_ai_filter_schema_path()
            if ai_filter_schema.exists():
                self._ensure_ai_filter_schema(conn)
                conn.executescript(ai_filter_schema.read_text(encoding="utf-8"))
            self._ensure_ai_filter_schema(conn)

        conn.commit()

    def _ensure_news_schema_columns(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(news_items)")
        existing_columns = {str(row[1]) for row in cursor.fetchall()}
        required_columns = {
            "summary": "ALTER TABLE news_items ADD COLUMN summary TEXT DEFAULT ''",
            "source_metadata_json": (
                "ALTER TABLE news_items ADD COLUMN source_metadata_json TEXT DEFAULT '{}'"
            ),
        }
        for column_name, statement in required_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(statement)

    def _ensure_ai_filter_schema(self, conn: sqlite3.Connection) -> None:
        cursor = conn.execute("PRAGMA table_info(ai_filter_analyzed_news)")
        table_info = cursor.fetchall()
        if not table_info:
            return

        existing_columns = {str(row[1]) for row in table_info}
        existing_pk = tuple(
            str(row[1])
            for row in sorted(
                (row for row in table_info if int(row[5]) > 0),
                key=lambda row: int(row[5]),
            )
        )
        required_pk = (
            "news_item_id",
            "source_type",
            "interests_file",
            "prompt_hash",
            "tag_version",
            "model_key",
        )
        if {"tag_version", "model_key"}.issubset(existing_columns) and existing_pk == required_pk:
            self._create_ai_filter_indexes(conn)
            return

        tag_version_expr = "CAST(tag_version AS INTEGER)" if "tag_version" in existing_columns else "CAST(0 AS INTEGER)"
        model_key_expr = "CAST(model_key AS TEXT)" if "model_key" in existing_columns else "CAST('' AS TEXT)"
        conn.executescript(
            """
            DROP TABLE IF EXISTS ai_filter_analyzed_news__migrated;
            CREATE TABLE ai_filter_analyzed_news__migrated (
                news_item_id INTEGER NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'hotlist',
                interests_file TEXT NOT NULL DEFAULT 'ai_interests.txt',
                prompt_hash TEXT NOT NULL,
                tag_version INTEGER NOT NULL DEFAULT 0,
                model_key TEXT NOT NULL DEFAULT '',
                matched INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (news_item_id, source_type, interests_file, prompt_hash, tag_version, model_key)
            );
            """
        )
        conn.execute(
            f"""
            INSERT OR REPLACE INTO ai_filter_analyzed_news__migrated (
                news_item_id,
                source_type,
                interests_file,
                prompt_hash,
                tag_version,
                model_key,
                matched,
                created_at
            )
            SELECT
                news_item_id,
                source_type,
                interests_file,
                prompt_hash,
                {tag_version_expr},
                {model_key_expr},
                MAX(matched),
                MAX(created_at)
            FROM ai_filter_analyzed_news
            GROUP BY
                news_item_id,
                source_type,
                interests_file,
                prompt_hash,
                {tag_version_expr},
                {model_key_expr}
            """
        )
        conn.executescript(
            """
            DROP TABLE ai_filter_analyzed_news;
            ALTER TABLE ai_filter_analyzed_news__migrated RENAME TO ai_filter_analyzed_news;
            """
        )
        self._create_ai_filter_indexes(conn)

    def _create_ai_filter_indexes(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_analyzed_news_lookup
                ON ai_filter_analyzed_news(source_type, interests_file, prompt_hash, tag_version, model_key);
            CREATE INDEX IF NOT EXISTS idx_analyzed_news_hash
                ON ai_filter_analyzed_news(interests_file, prompt_hash, tag_version);
            CREATE INDEX IF NOT EXISTS idx_analyzed_news_news_id
                ON ai_filter_analyzed_news(news_item_id, interests_file, prompt_hash, tag_version, model_key);
            """
        )

    def close_connection(self, db_path: str) -> None:
        conn = self.db_connections.pop(db_path, None)
        if conn is not None:
            conn.close()

    def close_all(self) -> None:
        for db_path in list(self.db_connections):
            self.close_connection(db_path)
