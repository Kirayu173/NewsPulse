# coding=utf-8
"""Shared CLI utilities."""

import sys
from pathlib import Path
from typing import Dict, Optional


def configure_console_output() -> None:
    """Avoid crashing on Windows consoles that cannot encode emoji."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def resolve_data_dir(config: Optional[Dict] = None) -> Path:
    """Resolve the configured output directory."""
    if not config:
        return Path("output")

    storage = config.get("STORAGE", {})
    local = storage.get("LOCAL", {})
    return Path(local.get("DATA_DIR", "output"))
