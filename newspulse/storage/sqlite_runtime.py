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
            self.init_tables(conn, db_type)
            self.db_connections[db_path] = conn
        return self.db_connections[db_path]

    def get_schema_path(self, db_type: str = "news") -> Path:
        return Path(__file__).parent / "schema.sql"

    def get_ai_filter_schema_path(self) -> Path:
        return Path(__file__).parent / "ai_filter_schema.sql"

    def init_tables(self, conn: sqlite3.Connection, db_type: str = "news") -> None:
        schema_path = self.get_schema_path(db_type)
        if schema_path.exists():
            conn.executescript(schema_path.read_text(encoding="utf-8"))

        if db_type == "news":
            ai_filter_schema = self.get_ai_filter_schema_path()
            if ai_filter_schema.exists():
                conn.executescript(ai_filter_schema.read_text(encoding="utf-8"))

        conn.commit()

    def close_connection(self, db_path: str) -> None:
        conn = self.db_connections.pop(db_path, None)
        if conn is not None:
            conn.close()

    def close_all(self) -> None:
        for db_path in list(self.db_connections):
            self.close_connection(db_path)
