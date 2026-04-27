# coding=utf-8
"""Platform-specific title formatting helpers for notifications and HTML."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from newspulse.workflow.render.helpers import clean_title, format_rank_display, html_escape

NEW_MARKER = "\U0001F195 "
COUNT_UNIT = "\u6b21"


class PlatformFormat(str, Enum):
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WEWORK = "wework"
    BARK = "bark"
    TELEGRAM = "telegram"
    NTFY = "ntfy"
    SLACK = "slack"
    HTML = "html"
    PLAIN = "plain"


_MARKDOWN_LINK_PLATFORMS = {
    PlatformFormat.FEISHU,
    PlatformFormat.DINGTALK,
    PlatformFormat.WEWORK,
    PlatformFormat.BARK,
    PlatformFormat.NTFY,
}

_CODE_SUFFIX_PLATFORMS = {
    PlatformFormat.TELEGRAM,
    PlatformFormat.NTFY,
    PlatformFormat.SLACK,
}

_HTML_FONT_SUFFIX_PLATFORMS = {
    PlatformFormat.FEISHU,
    PlatformFormat.HTML,
}


def format_title_for_platform(
    platform: str,
    title_data: Mapping[str, Any],
    show_source: bool = True,
    show_keyword: bool = False,
) -> str:
    """Format one title payload for the requested notification or HTML platform."""

    platform_format = _coerce_platform(platform)
    payload = _normalize_payload(title_data)
    title_text = clean_title(payload["title"])
    link_url = payload["mobile_url"] or payload["url"]
    rank_display = format_rank_display(
        payload["ranks"],
        payload["rank_threshold"],
        platform_format.value,
    )
    prefix = _build_prefix(
        platform_format,
        source_name=payload["source_name"],
        keyword=payload["matched_keyword"],
        show_source=show_source,
        show_keyword=show_keyword,
    )
    new_prefix = NEW_MARKER if payload["is_new"] and platform_format is not PlatformFormat.HTML else ""
    result = f"{prefix}{new_prefix}{_format_title_core(platform_format, title_text, link_url)}"
    result = _append_suffixes(
        result,
        platform_format,
        rank_display=rank_display,
        time_display=payload["time_display"],
        count=payload["count"],
    )
    if payload["is_new"] and platform_format is PlatformFormat.HTML:
        return f'<div class="new-title">{NEW_MARKER}{result}</div>'
    return result


def _coerce_platform(platform: str) -> PlatformFormat:
    normalized = str(platform or "").strip().lower()
    for item in PlatformFormat:
        if item.value == normalized:
            return item
    return PlatformFormat.PLAIN


def _normalize_payload(title_data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": str(title_data.get("title", "") or ""),
        "source_name": str(title_data.get("source_name", "") or ""),
        "time_display": str(title_data.get("time_display", "") or ""),
        "count": _coerce_positive_int(title_data.get("count"), fallback=1),
        "ranks": _normalize_ranks(title_data),
        "rank_threshold": _coerce_positive_int(title_data.get("rank_threshold"), fallback=10),
        "url": str(title_data.get("url", "") or ""),
        "mobile_url": str(title_data.get("mobile_url", "") or title_data.get("mobileUrl", "") or ""),
        "is_new": bool(title_data.get("is_new", False)),
        "matched_keyword": str(title_data.get("matched_keyword", "") or ""),
    }


def _normalize_ranks(title_data: Mapping[str, Any]) -> list[int]:
    ranks = title_data.get("ranks", [])
    normalized: list[int] = []
    if isinstance(ranks, Sequence) and not isinstance(ranks, (str, bytes)):
        for rank in ranks:
            parsed = _coerce_positive_int(rank)
            if parsed is not None:
                normalized.append(parsed)
    if not normalized:
        fallback_rank = _coerce_positive_int(title_data.get("rank"))
        if fallback_rank is not None:
            normalized.append(fallback_rank)
    return normalized


def _format_title_core(platform: PlatformFormat, title: str, link_url: str) -> str:
    if platform is PlatformFormat.HTML:
        escaped_title = html_escape(title)
        if link_url:
            return (
                f'<a href="{html_escape(link_url)}" target="_blank" '
                f'class="news-link">{escaped_title}</a>'
            )
        return f'<span class="no-link">{escaped_title}</span>'

    if platform is PlatformFormat.TELEGRAM:
        escaped_title = html_escape(title)
        if link_url:
            return f'<a href="{html_escape(link_url)}">{escaped_title}</a>'
        return escaped_title

    if platform is PlatformFormat.SLACK and link_url:
        return f"<{link_url}|{title}>"

    if platform in _MARKDOWN_LINK_PLATFORMS and link_url:
        return f"[{title}]({link_url})"

    return title


def _build_prefix(
    platform: PlatformFormat,
    *,
    source_name: str,
    keyword: str,
    show_source: bool,
    show_keyword: bool,
) -> str:
    if show_source and source_name:
        return _format_label(platform, source_name, is_keyword=False)
    if show_keyword and keyword:
        return _format_label(platform, keyword, is_keyword=True)
    return ""


def _format_label(platform: PlatformFormat, value: str, *, is_keyword: bool) -> str:
    if platform is PlatformFormat.HTML:
        class_name = "keyword-tag" if is_keyword else "source-tag"
        return f'<span class="{class_name}">[{html_escape(value)}]</span> '
    if platform is PlatformFormat.FEISHU:
        color = "blue" if is_keyword else "grey"
        return f"<font color='{color}'>[{value}]</font> "
    if platform is PlatformFormat.TELEGRAM and is_keyword:
        return f"<b>[{html_escape(value)}]</b> "
    if platform is PlatformFormat.SLACK and is_keyword:
        return f"*[{value}]* "
    return f"[{value}] "


def _append_suffixes(
    result: str,
    platform: PlatformFormat,
    *,
    rank_display: str,
    time_display: str,
    count: int,
) -> str:
    if rank_display:
        result += f" {rank_display}"
    if time_display:
        result += _format_time_suffix(platform, time_display)
    if count > 1:
        result += _format_count_suffix(platform, count)
    return result


def _format_time_suffix(platform: PlatformFormat, time_display: str) -> str:
    if platform in _HTML_FONT_SUFFIX_PLATFORMS:
        suffix = _escape_if_needed(platform, time_display)
        return f" <font color='grey'>- {suffix}</font>"
    if platform in _CODE_SUFFIX_PLATFORMS:
        return f" {_wrap_code(platform, f'- {time_display}')}"
    return f" - {time_display}"


def _format_count_suffix(platform: PlatformFormat, count: int) -> str:
    text = f"({count}{COUNT_UNIT})"
    if platform in _HTML_FONT_SUFFIX_PLATFORMS:
        return f" <font color='green'>{text}</font>"
    if platform in _CODE_SUFFIX_PLATFORMS:
        return f" {_wrap_code(platform, text)}"
    return f" {text}"


def _wrap_code(platform: PlatformFormat, text: str) -> str:
    if platform is PlatformFormat.TELEGRAM:
        return f"<code>{html_escape(text)}</code>"
    return f"`{text}`"


def _escape_if_needed(platform: PlatformFormat, text: str) -> str:
    if platform in {PlatformFormat.HTML, PlatformFormat.TELEGRAM}:
        return html_escape(text)
    return text


def _coerce_positive_int(value: Any, *, fallback: int | None = None) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    if number > 0:
        return number
    return fallback
