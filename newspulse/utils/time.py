# coding=utf-8
"""Shared timezone-aware date and time helpers."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Optional

import pytz

from newspulse.utils.logging import get_logger

DEFAULT_TIMEZONE = "Asia/Shanghai"
logger = get_logger(__name__)


def get_configured_time(timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """Return the current localized time for the configured timezone."""

    return datetime.now(_resolve_timezone(timezone))



def format_date_folder(date: Optional[str] = None, timezone: str = DEFAULT_TIMEZONE) -> str:
    """Return the report date folder name in ISO format."""

    if date:
        return str(date)
    return get_configured_time(timezone).strftime("%Y-%m-%d")



def format_time_filename(timezone: str = DEFAULT_TIMEZONE) -> str:
    """Return the current time formatted for file names."""

    return get_configured_time(timezone).strftime("%H-%M")



def get_current_time_display(timezone: str = DEFAULT_TIMEZONE) -> str:
    """Return the current localized time formatted for display."""

    return get_configured_time(timezone).strftime("%H:%M")



def convert_time_for_display(time_str: str) -> str:
    """Convert ``HH-MM`` file-name time strings to ``HH:MM`` display strings."""

    if time_str and "-" in time_str and len(time_str) == 5:
        return time_str.replace("-", ":")
    return time_str



def format_iso_time_friendly(
    iso_time: str,
    timezone: str = DEFAULT_TIMEZONE,
    include_date: bool = True,
) -> str:
    """Render an ISO-like timestamp in the configured local timezone."""

    normalized = str(iso_time or "").strip()
    if not normalized:
        return ""

    parsed = _parse_iso_time(normalized)
    if parsed is None:
        return _fallback_iso_display(normalized, include_date)

    localized = parsed.astimezone(_resolve_timezone(timezone))
    return localized.strftime("%m-%d %H:%M" if include_date else "%H:%M")



def is_within_days(
    iso_time: str,
    max_days: int,
    timezone: str = DEFAULT_TIMEZONE,
) -> bool:
    """Return whether the timestamp is within the requested number of days."""

    normalized = str(iso_time or "").strip()
    if not normalized or max_days <= 0:
        return True

    parsed = _parse_iso_time(normalized)
    if parsed is None:
        return True

    now = get_configured_time(timezone)
    delta = now - parsed.astimezone(now.tzinfo)
    return delta.total_seconds() <= max_days * 24 * 60 * 60



def calculate_days_old(iso_time: str, timezone: str = DEFAULT_TIMEZONE) -> Optional[float]:
    """Return the age of the timestamp in days, or ``None`` when parsing fails."""

    normalized = str(iso_time or "").strip()
    if not normalized:
        return None

    parsed = _parse_iso_time(normalized)
    if parsed is None:
        return None

    now = get_configured_time(timezone)
    delta = now - parsed.astimezone(now.tzinfo)
    return delta.total_seconds() / (24 * 60 * 60)



def _parse_iso_time(iso_time: str) -> Optional[datetime]:
    """Parse an ISO-like timestamp and return an aware ``datetime`` in UTC when naive."""

    normalized = str(iso_time or "").strip()
    if not normalized:
        return None

    for candidate in _iter_iso_candidates(normalized):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return pytz.UTC.localize(parsed)
        return parsed
    return None



def _iter_iso_candidates(iso_time: str) -> list[str]:
    candidates = [iso_time]
    if iso_time.endswith("Z"):
        candidates.insert(0, iso_time[:-1] + "+00:00")
    if "T" in iso_time:
        candidates.append(iso_time.replace("T", " "))
    without_fraction = _strip_fractional_seconds(iso_time)
    if without_fraction:
        candidates.append(without_fraction)
        if without_fraction.endswith("Z"):
            candidates.append(without_fraction[:-1] + "+00:00")
        if "T" in without_fraction:
            candidates.append(without_fraction.replace("T", " "))

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped



def _fallback_iso_display(iso_time: str, include_date: bool) -> str:
    """Return a best-effort ``MM-DD HH:MM`` preview for invalid timestamps."""

    if "T" not in iso_time:
        return iso_time
    date_part, _, remainder = iso_time.partition("T")
    if len(date_part) < 10:
        return iso_time
    month_day = date_part[5:10]
    time_part = remainder[:5]
    if len(time_part) != 5:
        return iso_time
    return f"{month_day} {time_part}" if include_date else time_part



def _strip_fractional_seconds(iso_time: str) -> str | None:
    match = re.match(
        r"^(?P<base>.*\d{2}:\d{2}:\d{2})\.(?P<fraction>\d+)(?P<suffix>Z|[+-]\d{2}:\d{2})?$",
        iso_time,
    )
    if not match:
        return None
    return f"{match.group('base')}{match.group('suffix') or ''}"



def _resolve_timezone(timezone: str):
    try:
        return pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        logger.warning(
            "[time] Unknown timezone '%s', falling back to %s",
            timezone,
            DEFAULT_TIMEZONE,
        )
        return pytz.timezone(DEFAULT_TIMEZONE)
