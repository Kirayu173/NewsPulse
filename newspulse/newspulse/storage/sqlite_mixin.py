# coding=utf-8
"""Compatibility shim for the legacy SQLite mixin import."""


class SQLiteStorageMixin:
    """Deprecated placeholder kept only for import compatibility."""

    def __init__(self, *args, **kwargs):
        raise TypeError(
            "SQLiteStorageMixin is no longer a concrete implementation. "
            "Use LocalStorageBackend or the repositories under newspulse.storage.repos."
        )
