# coding=utf-8
"""Shared helpers for builtin source handlers."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from newspulse.crawler.sources.base import SourceClient, SourceItem


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _first_nonempty_line(value: object) -> str:
    for line in str(value or "").splitlines():
        cleaned = _clean_text(line)
        if cleaned:
            return cleaned
    return ""

def _item(title: object, url: object = "", mobile_url: object = "") -> SourceItem:
    return SourceItem(
        title=_clean_text(title),
        url=_clean_text(url),
        mobile_url=_clean_text(mobile_url),
    )

def _sort_items(rows: Iterable[Tuple[str, SourceItem]]) -> List[SourceItem]:
    return [item for _, item in sorted(rows, key=lambda row: row[0], reverse=True)]

def _feed_items(client: SourceClient, url: str) -> List[SourceItem]:
    feed = client.get_feed(url)
    items: List[SourceItem] = []
    for entry in getattr(feed, "entries", []):
        title = _clean_text(entry.get("title"))
        link = _clean_text(entry.get("link"))
        if title and link:
            items.append(_item(title, link))
    return items

