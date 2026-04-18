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


def fetch_36kr_quick(client: SourceClient) -> List[SourceItem]:
    base_url = "https://www.36kr.com"
    soup = client.get_soup(f"{base_url}/newsflashes")
    items: List[SourceItem] = []
    for node in soup.select(".newsflash-item"):
        link = node.select_one("a.item-title")
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

def fetch_baidu(client: SourceClient) -> List[SourceItem]:
    text = client.get_text("https://top.baidu.com/board?tab=realtime")
    match = re.search(r"<!--s-data:(.*?)-->", text, re.S)
    if not match:
        raise ValueError("Cannot parse baidu hot board payload")
    data = json.loads(match.group(1))
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("cards", [{}])[0].get("content", []):
        if entry.get("isTop"):
            continue
        title = entry.get("word")
        url = entry.get("rawUrl")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_bilibili_hot_search(client: SourceClient) -> List[SourceItem]:
    data = client.get_json("https://s.search.bilibili.com/main/hotword?limit=30")
    items: List[SourceItem] = []
    for entry in data.get("list", []):
        keyword = entry.get("keyword")
        title = entry.get("show_name") or keyword
        if keyword and title:
            items.append(
                _item(
                    title,
                    f"https://search.bilibili.com/all?keyword={quote(str(keyword))}",
                )
            )
    return items

def _fetch_bilibili_videos(client: SourceClient, url: str) -> List[SourceItem]:
    data = client.get_json(url)
    items: List[SourceItem] = []
    for video in data.get("data", {}).get("list", []):
        bvid = video.get("bvid")
        title = video.get("title")
        if bvid and title:
            items.append(_item(title, f"https://www.bilibili.com/video/{bvid}"))
    return items

def fetch_bilibili_hot_video(client: SourceClient) -> List[SourceItem]:
    return _fetch_bilibili_videos(
        client, "https://api.bilibili.com/x/web-interface/popular"
    )

def fetch_bilibili_ranking(client: SourceClient) -> List[SourceItem]:
    return _fetch_bilibili_videos(
        client, "https://api.bilibili.com/x/web-interface/ranking/v2"
    )

def fetch_douban(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie",
        headers={"Referer": "https://movie.douban.com/"},
    )
    items: List[SourceItem] = []
    for movie in data.get("items", []):
        movie_id = movie.get("id")
        title = movie.get("title")
        if movie_id and title:
            items.append(_item(title, f"https://movie.douban.com/subject/{movie_id}"))
    return items

def fetch_douyin(client: SourceClient) -> List[SourceItem]:
    client.request("GET", "https://login.douyin.com/")
    data = client.get_json(
        "https://www.douyin.com/aweme/v1/web/hot/search/list/"
        "?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("word_list", []):
        item_id = entry.get("sentence_id")
        title = entry.get("word")
        if item_id and title:
            items.append(_item(title, f"https://www.douyin.com/hot/{item_id}"))
    return items

def fetch_ifeng(client: SourceClient) -> List[SourceItem]:
    html = client.get_text("https://www.ifeng.com/")
    match = re.search(r"var\s+allData\s*=\s*(\{[\s\S]*?\});", html)
    if not match:
        raise ValueError("Cannot parse ifeng payload")
    data = json.loads(match.group(1))
    items: List[SourceItem] = []
    for entry in data.get("hotNews1", []):
        title = entry.get("title")
        url = entry.get("url")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_iqiyi_hot_ranklist(client: SourceClient) -> List[SourceItem]:
    url = (
        "https://mesh.if.iqiyi.com/portal/lw/v7/channel/card/videoTab"
        "?channelName=recommend&data_source=v7_rec_sec_hot_rank_list"
        "&tempId=85&count=30&block_id=hot_ranklist"
        "&device=14a4b5ba98e790dce6dc07482447cf48&from=webapp"
    )
    data = client.get_json(url, headers={"Referer": "https://www.iqiyi.com"})
    items: List[SourceItem] = []
    cards = data.get("items", [{}])[0].get("video", [{}])[0].get("data", [])
    for entry in cards:
        title = entry.get("title")
        page_url = entry.get("page_url")
        if title and page_url:
            items.append(_item(title, page_url))
    return items

def fetch_kuaishou(client: SourceClient) -> List[SourceItem]:
    html = client.get_text("https://www.kuaishou.com/?isHome=1")
    match = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.+?\});", html, re.S)
    if not match:
        raise ValueError("Cannot parse kuaishou hot list")
    data = json.loads(match.group(1))
    root_query = data.get("defaultClient", {}).get("ROOT_QUERY", {})
    hot_rank = root_query.get('visionHotRank({"page":"home"})', {})
    hot_rank_id = hot_rank.get("id")
    hot_rank_data = data.get("defaultClient", {}).get(hot_rank_id, {})
    items: List[SourceItem] = []
    for entry in hot_rank_data.get("items", []):
        detail = data.get("defaultClient", {}).get(entry.get("id"), {})
        if detail.get("tagType") == "置顶":
            continue
        title = detail.get("name")
        if title:
            items.append(
                _item(
                    title,
                    f"https://www.kuaishou.com/search/video?searchKey={quote(str(title))}",
                )
            )
    return items

def fetch_qqvideo_hotsearch(client: SourceClient) -> List[SourceItem]:
    payload = {
        "page_params": {
            "rank_channel_id": "100113",
            "rank_name": "HotSearch",
            "rank_page_size": "30",
            "tab_mvl_sub_mod_id": "792ac_19e77Sub_1b2",
            "tab_name": "热搜榜",
            "tab_type": "hot_rank",
            "tab_vl_data_src": "f5200deb4596bbf3",
            "page_id": "scms_shake",
            "page_type": "scms_shake",
            "source_key": "",
            "tag_id": "",
            "tag_type": "",
            "new_mark_label_enabled": "1",
        },
        "page_context": {"page_index": "1"},
        "flip_info": {
            "page_strategy_id": "",
            "page_module_id": "792ac_19e77",
            "module_strategy_id": {},
            "sub_module_id": "20251106065177",
            "flip_params": {
                "folding_screen_show_num": "",
                "is_mvl": "1",
                "mvl_strategy_info": (
                    '{"default_strategy_id":"06755800b45b49238582a6fa1ad0f5c5",'
                    '"default_version":"3836","hit_page_uuid":"b5080d97dc694a5fb50eb9e7c99326ac",'
                    '"hit_tab_info":null,"gray_status_info":null,"bypass_to_un_exp_id":""}'
                ),
                "mvl_sub_mod_id": "20251106065177",
                "pad_post_show_num": "",
                "pad_pro_post_show_num": "",
                "pad_pro_small_hor_pic_display_num": "",
                "pad_small_hor_pic_display_num": "",
                "page_id": "scms_shake",
                "page_num": "0",
                "page_type": "scms_shake",
                "post_show_num": "",
                "shake_size": "",
                "small_hor_pic_display_num": "",
                "source_key": "100113",
                "un_policy_id": "06755800b45b49238582a6fa1ad0f5c5",
                "un_strategy_id": "06755800b45b49238582a6fa1ad0f5c5",
            },
            "relace_children_key": [],
        },
    }
    response = client.request(
        "POST",
        "https://pbaccess.video.qq.com/trpc.vector_layout.page_view.PageService/getCard"
        "?video_appid=3000010&vversion_platform=2",
        headers={"Referer": "https://v.qq.com/"},
        json=payload,
    ).json()
    cards = (
        response.get("data", {})
        .get("card", {})
        .get("children_list", {})
        .get("list", {})
        .get("cards", [])
    )
    items: List[SourceItem] = []
    for entry in cards:
        params = entry.get("params", {})
        cid = entry.get("id")
        title = params.get("title")
        if cid and title:
            items.append(_item(title, f"https://v.qq.com/x/cover/{cid}.html"))
    return items

def fetch_tencent_hot(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://i.news.qq.com/web_backend/v2/getTagInfo?tagId=aEWqxLtdgmQ%3D",
        headers={"Referer": "https://news.qq.com/"},
    )
    items: List[SourceItem] = []
    tabs = data.get("data", {}).get("tabs", [])
    article_list = tabs[0].get("articleList", []) if tabs else []
    for entry in article_list:
        item_id = entry.get("id")
        title = entry.get("title")
        url = entry.get("link_info", {}).get("url")
        if item_id and title and url:
            items.append(_item(title, url))
    return items

def fetch_thepaper(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("hotNews", []):
        item_id = entry.get("contId")
        title = entry.get("name")
        if item_id and title:
            items.append(
                _item(
                    title,
                    f"https://www.thepaper.cn/newsDetail_forward_{item_id}",
                    f"https://m.thepaper.cn/newsDetail_forward_{item_id}",
                )
            )
    return items

def fetch_tieba(client: SourceClient) -> List[SourceItem]:
    data = client.get_json("https://tieba.baidu.com/hottopic/browse/topicList")
    items: List[SourceItem] = []
    for entry in data.get("data", {}).get("bang_topic", {}).get("topic_list", []):
        title = entry.get("topic_name")
        url = entry.get("topic_url")
        if title and url:
            items.append(_item(title, url))
    return items

def fetch_toutiao(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        cluster_id = entry.get("ClusterIdStr")
        title = entry.get("Title")
        if cluster_id and title:
            items.append(_item(title, f"https://www.toutiao.com/trending/{cluster_id}/"))
    return items

def fetch_weibo(client: SourceClient) -> List[SourceItem]:
    base_url = "https://s.weibo.com"
    url = f"{base_url}/top/summary?cate=realtimehot"
    soup = client.get_soup(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
            "Cookie": (
                "SUB=_2AkMWIuNSf8NxqwJRmP8dy2rhaoV2ygrEieKgfhKJJRMxHRl-yT9jqk86"
                "tRB6PaLNvQZR6zYUcYVT1zSjoSreQHidcUq7"
            ),
            "Referer": url,
        },
    )
    items: List[SourceItem] = []
    rows = soup.select("#pl_top_realtimehot table tbody tr")[1:]
    for row in rows:
        link = None
        for candidate in row.select("td.td-02 a"):
            href = candidate.get("href", "")
            if href and "javascript:void(0);" not in href:
                link = candidate
                break
        href = link.get("href", "") if link else ""
        title = link.get_text(" ", strip=True) if link else ""
        if title and href:
            items.append(_item(title, absolute_url(base_url, href)))
    return items

def fetch_zhihu(client: SourceClient) -> List[SourceItem]:
    data = client.get_json(
        "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true"
    )
    items: List[SourceItem] = []
    for entry in data.get("data", []):
        target = entry.get("target", {})
        link = target.get("link", {})
        url = link.get("url")
        title = target.get("title_area", {}).get("text")
        if title and url:
            items.append(_item(title, url))
    return items

