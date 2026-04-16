# coding=utf-8
"""Shared helpers for SQLite repositories."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from newspulse.storage.sqlite_runtime import SQLiteRuntime


class SQLiteRepositoryBase:
    """Delegate connection and schema helpers to the shared runtime."""

    def __init__(self, runtime: SQLiteRuntime):
        self.runtime = runtime

    def _get_connection(self, date: Optional[str] = None, db_type: str = "news") -> sqlite3.Connection:
        return self.runtime.get_connection(date, db_type)

    def _get_configured_time(self) -> datetime:
        return self.runtime.get_configured_time()

    def _format_date_folder(self, date: Optional[str] = None) -> str:
        return self.runtime.format_date_folder(date)

    def _format_time_filename(self) -> str:
        return self.runtime.format_time_filename()

    def _get_schema_path(self, db_type: str = "news") -> Path:
        return self.runtime.get_schema_path(db_type)

    def _get_ai_filter_schema_path(self) -> Path:
        return self.runtime.get_ai_filter_schema_path()

    def _init_tables(self, conn: sqlite3.Connection, db_type: str = "news") -> None:
        self.runtime.init_tables(conn, db_type)
