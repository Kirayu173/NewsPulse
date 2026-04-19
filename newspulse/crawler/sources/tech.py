# coding=utf-8
"""Builtin hotlist handlers."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
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


def fetch_chongbuluo_hot(client: SourceClient) -> List[SourceItem]:
    base_url = "https://www.chongbuluo.com/"
    soup = client.get_soup(f"{base_url}forum.php?mod=guide&view=hot")
    items: List[SourceItem] = []
    for node in soup.select(".bmw table tr"):
        link = node.select_one(".common .xst")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

def fetch_chongbuluo_latest(client: SourceClient) -> List[SourceItem]:
    return _feed_items(
        client, "https://www.chongbuluo.com/forum.php?mod=rss&view=newthread"
    )

def _coolapk_headers() -> Dict[str, str]:
    device_id = random_device_id()
    now = round(datetime.now().timestamp())
    hex_now = f"0x{now:x}"
    md5_now = md5_hex(str(now))
    token_source = (
        "token://com.coolapk.market/"
        "c67ef5943784d09750dcfbb31020f0ab?"
        f"{md5_now}${device_id}&com.coolapk.market"
    )
    token = md5_hex(base64_encode(token_source)) + device_id + hex_now
    return {
        "X-Requested-With": "XMLHttpRequest",
        "X-App-Id": "com.coolapk.market",
        "X-App-Token": token,
        "X-Sdk-Int": "29",
        "X-Sdk-Locale": "zh-CN",
        "X-App-Version": "11.0",
        "X-Api-Version": "11",
        "X-App-Code": "2101202",
        "User-Agent": (
            "Dalvik/2.1.0 (Linux; U; Android 10; Redmi K30 5G "
            "MIUI/V12.0.3.0.QGICMXM) "
            "+CoolMarket/11.0-2101202"
        ),
    }

def fetch_coolapk(client: SourceClient) -> List[SourceItem]:
    url = (
        "https://api.coolapk.com/v6/page/dataList?"
        "url=%2Ffeed%2FstatList%3FcacheExpires%3D300%26statType%3Dday"
        "%26sortField%3Ddetailnum%26title%3D%E4%BB%8A%E6%97%A5%E7%83%AD"
        "%E9%97%A8&title=%E4%BB%8A%E6%97%A5%E7%83%AD%E9%97%A8&subTitle=&page=1"
    )
    data = client.get_json(url, headers=_coolapk_headers())
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        item_id = entry.get("id")
        title = entry.get("editor_title")
        if not title:
            title = _first_nonempty_line(strip_html(entry.get("message", "")))
        href = entry.get("url", "")
        if item_id and title and href:
            items.append(_item(title, absolute_url("https://www.coolapk.com", href)))
    return items

def fetch_github_trending(client: SourceClient) -> List[SourceItem]:
    try:
        items = _fetch_github_trending_html(client)
    except Exception:
        items = []
    if items:
        return items
    return _fetch_github_trending_search_api(client)


def _fetch_github_trending_html(client: SourceClient) -> List[SourceItem]:
    base_url = "https://github.com"
    soup = client.get_soup("https://github.com/trending?spoken_language_code=")
    items: List[SourceItem] = []
    for node in soup.select("main .Box div[data-hpc] > article"):
        link = node.select_one("h2 a")
        href = link.get("href", "") if link else ""
        title = _clean_text(link.get_text(" ", strip=True) if link else "")
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items


def _fetch_github_trending_search_api(client: SourceClient) -> List[SourceItem]:
    created_after = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GITHUB_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = client.request(
        "GET",
        "https://api.github.com/search/repositories",
        headers=headers,
        params={
            "q": f"created:>{created_after}",
            "sort": "stars",
            "order": "desc",
            "per_page": 20,
        },
    )
    data = response.json()
    items: List[SourceItem] = []
    for entry in data.get("items", []):
        title = _clean_text(str(entry.get("full_name") or entry.get("name") or ""))
        url = str(entry.get("html_url") or "").strip()
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_ghxi(client: SourceClient) -> List[SourceItem]:
    soup = client.get_soup("https://www.ghxi.com/category/all")
    items: List[SourceItem] = []
    for node in soup.select(".sec-panel .sec-panel-body .post-loop li"):
        link = node.select_one(".item-content .item-title a")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, href))
    return items

def fetch_hackernews(client: SourceClient) -> List[SourceItem]:
    base_url = "https://hn.aimaker.dev"
    soup = client.get_soup(f"{base_url}/category/top")
    items: List[SourceItem] = []
    for node in soup.select("article"):
        title_node = node.select_one("div.flex.items-start.gap-2 a[href]")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        translated_url = absolute_url(base_url, title_node.get("href", "")) if title_node else ""
        hn_url = ""
        for candidate in node.select("a[href]"):
            href = candidate.get("href", "")
            if "news.ycombinator.com/item?id=" in href:
                hn_url = href
                break
        final_url = hn_url or translated_url
        if title and final_url:
            items.append(_item(title, final_url, translated_url))
    return items

def fetch_ithome(client: SourceClient) -> List[SourceItem]:
    soup = client.get_soup("https://www.ithome.com/list/")
    items: List[SourceItem] = []
    for node in soup.select("#list > div.fl > ul > li"):
        link = node.select_one("a.t")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if not title or not href:
            continue
        if "lapin" in href or any(word in title for word in ("神券", "优惠", "补贴", "京东")):
            continue
        items.append(_item(title, href))
    return items

def fetch_juejin(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://api.juejin.cn/content_api/v1/content/article_rank"
        "?category_id=1&type=hot&spider=0"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        content = entry.get("content", {})
        content_id = content.get("content_id")
        title = content.get("title")
        if content_id and title:
            items.append(_item(title, f"https://juejin.cn/post/{content_id}"))
    return items

def fetch_kaopu(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://kaopustorage.blob.core.windows.net/news-prod/news_list_hans_0.json"
    )
    items: List[SourceItem] = []
    for entry in data:
        if entry.get("publisher") in {"财新", "公视"}:
            continue
        title = entry.get("title")
        url = entry.get("link")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_nowcoder(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        f"https://gw-c.nowcoder.com/api/sparta/hot-search/top-hot-pc?size=20&_={int(datetime.now().timestamp() * 1000)}&t="
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("result", []):
        item_type = entry.get("type")
        title = entry.get("title")
        item_id = entry.get("id")
        if item_type == 74 and entry.get("uuid") and title:
            items.append(
                _item(title, f"https://www.nowcoder.com/feed/main/detail/{entry['uuid']}")
            )
        elif item_type == 0 and item_id and title:
            items.append(_item(title, f"https://www.nowcoder.com/discuss/{item_id}"))
    return items

def fetch_pcbeta_windows11(client: SourceClient) -> List[SourceItem]:
    return _feed_items(
        client, "https://bbs.pcbeta.com/forum.php?mod=rss&fid=563&auth=0"
    )

def fetch_producthunt(client: SourceClient) -> List[SourceItem]:
    token = os.environ.get("PRODUCTHUNT_API_TOKEN", "").strip()
    if not token:
        # Product Hunt keeps a public Atom feed available even when no API token
        # is configured, which avoids leaving this source permanently unusable.
        return _feed_items(client, "https://www.producthunt.com/feed")
    query = """
    query {
      posts(first: 30, order: VOTES) {
        edges {
          node {
            id
            name
            url
            slug
          }
        }
      }
    }
    """
    response = client.request(
        "POST",
        "https://api.producthunt.com/v2/api/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={"query": query},
    ).json()
    items: List[SourceItem] = []
    for edge in response.get("data", {}).get("posts", {}).get("edges", []):
        node = edge.get("node", {})
        item_id = node.get("id")
        title = node.get("name")
        url = node.get("url") or (
            f"https://www.producthunt.com/posts/{node.get('slug')}"
            if node.get("slug")
            else ""
        )
        if item_id and title and url:
            items.append(_item(title, url))
    return items

def fetch_smzdm(client: SourceClient) -> List[SourceItem]:
    soup = client.get_soup("https://post.smzdm.com/hot_1/")
    items: List[SourceItem] = []
    for node in soup.select("#feed-main-list .z-feed-title"):
        link = node.select_one("a")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, href))
    return items

def fetch_solidot(client: SourceClient) -> List[SourceItem]:
    base_url = "https://www.solidot.org"
    soup = client.get_soup(base_url)
    items: List[SourceItem] = []
    for node in soup.select(".block_m"):
        link = node.select_one(".bg_htit a:last-child")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

def fetch_sspai(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://sspai.com/api/v1/article/tag/page/get"
        f"?limit=30&offset=0&created_at={int(datetime.now().timestamp() * 1000)}"
        "&tag=%E7%83%AD%E9%97%A8%E6%96%87%E7%AB%A0&released=false"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        item_id = entry.get("id")
        title = entry.get("title")
        if item_id and title:
            items.append(_item(title, f"https://sspai.com/post/{item_id}"))
    return items

