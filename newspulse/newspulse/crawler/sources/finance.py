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


def _cls_params(extra: Dict[str, str] | None = None) -> Sequence[Tuple[str, str]]:
    params = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
    }
    if extra:
        params.update(extra)
    ordered = sorted(params.items())
    query = urlencode(ordered)
    sign = md5_hex(sha1_hex(query))
    ordered.append(("sign", sign))
    return ordered

def fetch_cls_depth(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://www.cls.cn/v3/depth/home/assembled/1000",
        params=_cls_params(),
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("depth_list", []):
        item_id = entry.get("id")
        title = entry.get("title") or entry.get("brief")
        mobile_url = entry.get("shareurl", "")
        if item_id and title:
            items.append(
                _item(title, f"https://www.cls.cn/detail/{item_id}", mobile_url)
            )
    return items

def fetch_cls_hot(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://www.cls.cn/v2/article/hot/list",
        params=_cls_params(),
    )
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        item_id = entry.get("id")
        title = entry.get("title") or entry.get("brief")
        mobile_url = entry.get("shareurl", "")
        if item_id and title:
            items.append(
                _item(title, f"https://www.cls.cn/detail/{item_id}", mobile_url)
            )
    return items

def fetch_cls_telegraph(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://www.cls.cn/nodeapi/updateTelegraphList",
        params=_cls_params(),
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("roll_data", []):
        if entry.get("is_ad"):
            continue
        item_id = entry.get("id")
        title = entry.get("title") or entry.get("brief")
        mobile_url = entry.get("shareurl", "")
        if item_id and title:
            items.append(
                _item(title, f"https://www.cls.cn/detail/{item_id}", mobile_url)
            )
    return items

def fetch_gelonghui(client: SourceClient) -> List[SourceItem]:
    base_url = "https://www.gelonghui.com"
    soup = client.get_soup(f"{base_url}/news/")
    items: List[SourceItem] = []
    for node in soup.select(".article-content"):
        link = node.select_one(".detail-right > a")
        href = link.get("href", "") if link else ""
        title_node = link.select_one("h2") if link else None
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

def fetch_jin10(client: SourceClient) -> List[SourceItem]:
    raw_data = client.get_text(
        f"https://www.jin10.com/flash_newest.js?t={int(datetime.now().timestamp() * 1000)}"
    )
    json_str = re.sub(r"^var\s+newest\s*=\s*", "", raw_data).rstrip(";").strip()
    data = json.loads(json_str)
    items: List[SourceItem] = []
    for entry in data:
        channels = entry.get("channel") or []
        if 5 in channels:
            continue
        payload = entry.get("data", {})
        text = payload.get("title") or payload.get("content") or ""
        cleaned = re.sub(r"</?b>", "", text)
        match = re.match(r"^【([^】]*)】(.*)$", cleaned)
        title = match.group(1) if match else cleaned
        item_id = entry.get("id")
        if item_id and title:
            items.append(_item(title, f"https://flash.jin10.com/detail/{item_id}"))
    return items

def fetch_wallstreetcn_quick(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("items", []):
        title = entry.get("title") or entry.get("content_text")
        url = entry.get("uri")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_wallstreetcn_news(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://api-one.wallstcn.com/apiv1/content/information-flow"
        "?channel=global-channel&accept=article&limit=30"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("items", []):
        if entry.get("resource_type") in {"theme", "ad"}:
            continue
        resource = entry.get("resource", {})
        if resource.get("type") == "live":
            continue
        title = resource.get("title") or resource.get("content_short")
        url = resource.get("uri")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_wallstreetcn_hot(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://api-one.wallstcn.com/apiv1/content/articles/hot?period=all"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("day_items", []):
        title = entry.get("title")
        url = entry.get("uri")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_xueqiu_hotstock(client: SourceClient) -> List[SourceItem]:
    client.request("GET", "https://xueqiu.com/hq")
    data = client.get_json(
        "https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size=30&_type=10&type=10"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("items", []):
        if entry.get("ad"):
            continue
        code = entry.get("code")
        title = entry.get("name")
        if code and title:
            items.append(_item(title, f"https://xueqiu.com/s/{code}"))
    return items

