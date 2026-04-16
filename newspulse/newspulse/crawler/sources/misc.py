# coding=utf-8
"""Builtin hotlist handlers."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Sequence, Tuple
from urllib.parse import quote, urlencode

from newspulse.crawler.sources.base import (
    SourceClient,
    SourceItem,
    absolute_url,
    base64_encode,
    make_soup,
    md5_hex,
    random_device_id,
    sha1_hex,
    strip_html,
)
from newspulse.crawler.sources.common import (
    _clean_text,
    _first_nonempty_line,
    _feed_items,
    _item,
    _sort_items,
)


def fetch_cankaoxiaoxi(client: SourceClient) -> List[SourceItem]:
    channels = ("zhongguo", "guandian", "gj")
    rows: List[Tuple[str, SourceItem]] = []
    for channel in channels:
        data = client.get_json(
            f"https://china.cankaoxiaoxi.com/json/channel/{channel}/list.json"
        )
        for entry in data.get("list", []):
            payload = entry.get("data", {})
            title = payload.get("title")
            url = payload.get("url")
            publish_time = _clean_text(payload.get("publishTime"))
            if title and url:
                rows.append((publish_time, _item(title, url)))
    return _sort_items(rows)

def fetch_hupu(client: SourceClient) -> List[SourceItem]:
    html = client.get_text("https://bbs.hupu.com/topic-daily-hot")
    items: List[SourceItem] = []
    for path, title in re.findall(
        r'<a href="(\/[^"]+?\.html)"[^>]*class="p-title"[^>]*>([^<]+)<\/a>',
        html,
    ):
        final_title = _clean_text(title)
        if final_title:
            url = f"https://bbs.hupu.com{path}"
            items.append(_item(final_title, url, url))
    return items

def fetch_sputniknewscn(client: SourceClient) -> List[SourceItem]:
    base_url = "https://sputniknews.cn"
    soup = client.get_soup(f"{base_url}/services/widget/lenta/")
    items: List[SourceItem] = []
    for node in soup.select(".lenta__item"):
        link = node.select_one("a")
        href = link.get("href", "") if link else ""
        title_node = link.select_one(".lenta__item-text") if link else None
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

