# coding=utf-8
"""Builtin hotlist handlers."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlencode

from newspulse.crawler.sources.base import (
    SourceClient,
    SourceItem,
    absolute_url,
    base64_encode,
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
        return _enrich_github_trending_items(client, items)
    return _fetch_github_trending_search_api(client)


def _fetch_github_trending_html(client: SourceClient) -> List[SourceItem]:
    base_url = "https://github.com"
    soup = client.get_soup("https://github.com/trending?spoken_language_code=")
    items: List[SourceItem] = []
    for node in soup.select("main article.Box-row"):
        link = node.select_one("h2 a")
        href = link.get("href", "") if link else ""
        title = _normalize_github_repo_name(link.get_text(" ", strip=True) if link else "")
        if not title or not href:
            continue

        description = _clean_text(node.select_one("p").get_text(" ", strip=True) if node.select_one("p") else "")
        language = _clean_text(
            node.select_one('[itemprop="programmingLanguage"]').get_text(" ", strip=True)
            if node.select_one('[itemprop="programmingLanguage"]')
            else ""
        )
        stars_total = _extract_github_metric(node, r"/stargazers$")
        forks_total = _extract_github_metric(node, r"/forks$")
        stars_today = _extract_github_stars_today(node)

        items.append(
            _item(
                title,
                absolute_url(base_url, href),
                summary=description,
                metadata=_build_github_metadata(
                    full_name=title,
                    description=description,
                    language=language,
                    stars_total=stars_total,
                    forks_total=forks_total,
                    stars_today=stars_today,
                    source_variant="trending_html",
                    enriched_by="html",
                ),
            )
        )
    return items


def _enrich_github_trending_items(
    client: SourceClient,
    items: Sequence[SourceItem],
) -> List[SourceItem]:
    token = _github_api_token()
    if not token:
        return list(items)

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }
    enrich_limit = max(0, int(os.environ.get("GITHUB_TRENDING_ENRICH_LIMIT", "10") or 10))
    enriched_items: List[SourceItem] = []

    for index, item in enumerate(items):
        if enrich_limit and index >= enrich_limit:
            enriched_items.append(item)
            continue

        full_name = _resolve_github_full_name(item)
        if not full_name:
            enriched_items.append(item)
            continue

        try:
            payload = client.get_json(
                f"https://api.github.com/repos/{quote(full_name, safe='/')}",
                headers=headers,
            )
        except Exception:
            enriched_items.append(item)
            continue

        enriched_items.append(_merge_github_api_payload(item, payload))
    return enriched_items


def _fetch_github_trending_search_api(client: SourceClient) -> List[SourceItem]:
    created_after = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    token = _github_api_token()
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
        title = _normalize_github_repo_name(str(entry.get("full_name") or entry.get("name") or ""))
        url = str(entry.get("html_url") or "").strip()
        if not title or not url:
            continue

        summary = _clean_text(str(entry.get("description") or ""))
        items.append(
            _item(
                title,
                url,
                summary=summary,
                metadata=_build_github_metadata(
                    full_name=title,
                    description=summary,
                    language=_clean_text(str(entry.get("language") or "")),
                    stars_total=_coerce_compact_int(entry.get("stargazers_count")),
                    forks_total=_coerce_compact_int(entry.get("forks_count")),
                    topics=_normalize_github_topics(entry.get("topics")),
                    created_at=str(entry.get("created_at") or "").strip(),
                    pushed_at=str(entry.get("pushed_at") or "").strip(),
                    archived=bool(entry.get("archived", False)),
                    fork=bool(entry.get("fork", False)),
                    source_variant="search_api_fallback",
                    enriched_by="search_api",
                ),
            )
        )
    return items


def _merge_github_api_payload(item: SourceItem, payload: Dict[str, Any]) -> SourceItem:
    existing_metadata = dict(item.metadata or {})
    github_metadata = dict(existing_metadata.get("github") or {})
    api_topics = _normalize_github_topics(payload.get("topics"))
    merged_summary = _clean_text(str(payload.get("description") or item.summary or github_metadata.get("description") or ""))
    merged_full_name = _normalize_github_repo_name(
        str(payload.get("full_name") or github_metadata.get("full_name") or item.title or "")
    )

    github_metadata.update(
        {
            "full_name": merged_full_name,
            "description": merged_summary,
            "language": _clean_text(str(payload.get("language") or github_metadata.get("language") or "")),
            "stars_total": _coerce_compact_int(payload.get("stargazers_count"))
            if payload.get("stargazers_count") is not None
            else github_metadata.get("stars_total"),
            "forks_total": _coerce_compact_int(payload.get("forks_count"))
            if payload.get("forks_count") is not None
            else github_metadata.get("forks_total"),
            "topics": api_topics or _normalize_github_topics(github_metadata.get("topics")),
            "created_at": str(payload.get("created_at") or github_metadata.get("created_at") or "").strip(),
            "pushed_at": str(payload.get("pushed_at") or github_metadata.get("pushed_at") or "").strip(),
            "archived": bool(payload.get("archived", github_metadata.get("archived", False))),
            "fork": bool(payload.get("fork", github_metadata.get("fork", False))),
            "source_variant": str(github_metadata.get("source_variant") or "trending_html"),
            "enriched_by": "html+api",
        }
    )
    owner, repo = _split_github_full_name(merged_full_name)
    if owner:
        github_metadata["owner"] = owner
    if repo:
        github_metadata["repo"] = repo

    return SourceItem(
        title=merged_full_name or item.title,
        url=item.url,
        mobile_url=item.mobile_url,
        summary=merged_summary,
        metadata={
            **existing_metadata,
            "source_context_version": 1,
            "source_kind": "github_repository",
            "github": github_metadata,
        },
    )


def _build_github_metadata(
    *,
    full_name: str,
    description: str = "",
    language: str = "",
    stars_total: int | None = None,
    forks_total: int | None = None,
    stars_today: int | None = None,
    topics: Sequence[str] | None = None,
    created_at: str = "",
    pushed_at: str = "",
    archived: bool = False,
    fork: bool = False,
    source_variant: str,
    enriched_by: str,
) -> Dict[str, Any]:
    owner, repo = _split_github_full_name(full_name)
    github: Dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "full_name": full_name,
        "description": _clean_text(description),
        "language": _clean_text(language),
        "topics": list(_normalize_github_topics(topics)),
        "created_at": str(created_at or "").strip(),
        "pushed_at": str(pushed_at or "").strip(),
        "archived": bool(archived),
        "fork": bool(fork),
        "source_variant": source_variant,
        "enriched_by": enriched_by,
    }
    if stars_total is not None:
        github["stars_total"] = int(stars_total)
    if forks_total is not None:
        github["forks_total"] = int(forks_total)
    if stars_today is not None:
        github["stars_today"] = int(stars_today)
    return {
        "source_context_version": 1,
        "source_kind": "github_repository",
        "github": github,
    }


def _resolve_github_full_name(item: SourceItem) -> str:
    github = item.metadata.get("github") if isinstance(item.metadata, dict) else None
    if isinstance(github, dict):
        full_name = _normalize_github_repo_name(str(github.get("full_name") or ""))
        if full_name:
            return full_name
    return _normalize_github_repo_name(item.title)


def _extract_github_metric(node, href_pattern: str) -> int | None:
    for link in node.select("a[href]"):
        href = str(link.get("href") or "").strip()
        if not href or not re.search(href_pattern, href):
            continue
        return _coerce_compact_int(link.get_text(" ", strip=True))
    return None


def _extract_github_stars_today(node) -> int | None:
    for candidate in node.select("span, div"):
        text = _clean_text(candidate.get_text(" ", strip=True))
        if "stars today" not in text.lower():
            continue
        matched = re.search(r"([0-9][0-9,]*)\s+stars today", text, flags=re.IGNORECASE)
        if matched:
            return _coerce_compact_int(matched.group(1))
    return None


def _normalize_github_repo_name(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s*/\s*", "/", text)
    return text


def _split_github_full_name(full_name: str) -> Tuple[str, str]:
    if "/" not in full_name:
        return "", ""
    owner, repo = full_name.split("/", 1)
    return owner.strip(), repo.strip()


def _normalize_github_topics(value: Any) -> List[str]:
    if isinstance(value, str):
        parts = [segment.strip() for segment in value.split(",")]
        return [part for part in parts if part]
    if not isinstance(value, Sequence):
        return []
    topics: List[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            topics.append(text)
    return topics


def _coerce_compact_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = _clean_text(value).lower().replace(",", "")
    if not text:
        return None
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    matched = re.search(r"\d+(?:\.\d+)?", text)
    if not matched:
        return None
    return int(float(matched.group(0)) * multiplier)


def _github_api_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GITHUB_API_TOKEN", "").strip()

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

