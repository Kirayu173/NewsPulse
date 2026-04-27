# coding=utf-8
"""Shared logging helpers for NewsPulse runtime modules."""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_HANDLER_MARKER = "_newspulse_handler"
_DEFAULT_LOG_LEVEL = "INFO"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    normalized = name or "newspulse"
    if not normalized.startswith("newspulse"):
        normalized = f"newspulse.{normalized}"
    return logging.getLogger(normalized)


def build_log_message(event: str, **fields: Any) -> str:
    """Build a consistent runtime log line with optional structured fields."""

    normalized_event = str(event or "runtime").strip() or "runtime"
    parts = [f"[{normalized_event}]"]
    rendered_fields = _render_log_fields(fields)
    if rendered_fields:
        parts.append(rendered_fields)
    return " ".join(parts)


def configure_logging(
    level: str | int = _DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = None,
    json_mode: bool = False,
) -> logging.Logger:
    logger = get_logger("newspulse")
    logger.setLevel(_normalize_level(level))
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    formatter: logging.Formatter
    if json_mode:
        formatter = _JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _HANDLER_MARKER, True)
    logger.addHandler(console_handler)

    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        logger.addHandler(file_handler)

    return logger


def _normalize_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    normalized = str(level or _DEFAULT_LOG_LEVEL).strip().upper()
    return getattr(logging, normalized, logging.INFO)


def _render_log_fields(fields: dict[str, Any]) -> str:
    rendered: list[str] = []
    for key, value in fields.items():
        normalized_key = str(key or "").strip()
        if not normalized_key or value is None:
            continue
        normalized_value = _render_log_value(value)
        if normalized_value == "":
            continue
        rendered.append(f"{normalized_key}={normalized_value}")
    return " ".join(rendered)


def _render_log_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (list, tuple, set)):
        rendered_items = [_render_log_value(item) for item in value]
        rendered_items = [item for item in rendered_items if item != ""]
        return "[" + ",".join(rendered_items) + "]"

    text = str(value).strip()
    if not text:
        return ""
    if any(character.isspace() for character in text) or "=" in text:
        return json.dumps(text, ensure_ascii=False)
    return text
