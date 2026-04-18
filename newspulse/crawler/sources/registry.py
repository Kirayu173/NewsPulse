# coding=utf-8
"""Registry for builtin hotlist handlers."""

from __future__ import annotations

from typing import Callable, Dict, List

from newspulse.crawler.sources.base import SourceClient, SourceItem
from newspulse.crawler.sources.finance import (
    fetch_cls_depth,
    fetch_cls_hot,
    fetch_cls_telegraph,
    fetch_gelonghui,
    fetch_jin10,
    fetch_wallstreetcn_hot,
    fetch_wallstreetcn_news,
    fetch_wallstreetcn_quick,
    fetch_xueqiu_hotstock,
)
from newspulse.crawler.sources.mainland import (
    fetch_36kr_quick,
    fetch_baidu,
    fetch_bilibili_hot_search,
    fetch_bilibili_hot_video,
    fetch_bilibili_ranking,
    fetch_douban,
    fetch_douyin,
    fetch_ifeng,
    fetch_iqiyi_hot_ranklist,
    fetch_kuaishou,
    fetch_qqvideo_hotsearch,
    fetch_tencent_hot,
    fetch_thepaper,
    fetch_tieba,
    fetch_toutiao,
    fetch_weibo,
    fetch_zhihu,
)
from newspulse.crawler.sources.misc import (
    fetch_cankaoxiaoxi,
    fetch_hupu,
    fetch_sputniknewscn,
)
from newspulse.crawler.sources.tech import (
    fetch_chongbuluo_hot,
    fetch_chongbuluo_latest,
    fetch_coolapk,
    fetch_github_trending,
    fetch_ghxi,
    fetch_hackernews,
    fetch_ithome,
    fetch_juejin,
    fetch_kaopu,
    fetch_nowcoder,
    fetch_pcbeta_windows11,
    fetch_producthunt,
    fetch_smzdm,
    fetch_solidot,
    fetch_sspai,
)


SourceHandler = Callable[[SourceClient], List[SourceItem]]


SOURCE_REGISTRY: Dict[str, SourceHandler] = {
    "36kr": fetch_36kr_quick,
    "36kr-quick": fetch_36kr_quick,
    "baidu": fetch_baidu,
    "bilibili": fetch_bilibili_hot_search,
    "bilibili-hot-search": fetch_bilibili_hot_search,
    "bilibili-hot-video": fetch_bilibili_hot_video,
    "bilibili-ranking": fetch_bilibili_ranking,
    "cankaoxiaoxi": fetch_cankaoxiaoxi,
    "chongbuluo": fetch_chongbuluo_hot,
    "chongbuluo-hot": fetch_chongbuluo_hot,
    "chongbuluo-latest": fetch_chongbuluo_latest,
    "cls": fetch_cls_telegraph,
    "cls-depth": fetch_cls_depth,
    "cls-hot": fetch_cls_hot,
    "cls-telegraph": fetch_cls_telegraph,
    "coolapk": fetch_coolapk,
    "douban": fetch_douban,
    "douyin": fetch_douyin,
    "gelonghui": fetch_gelonghui,
    "github": fetch_github_trending,
    "github-trending-today": fetch_github_trending,
    "ghxi": fetch_ghxi,
    "hackernews": fetch_hackernews,
    "hupu": fetch_hupu,
    "ifeng": fetch_ifeng,
    "iqiyi": fetch_iqiyi_hot_ranklist,
    "iqiyi-hot-ranklist": fetch_iqiyi_hot_ranklist,
    "ithome": fetch_ithome,
    "jin10": fetch_jin10,
    "juejin": fetch_juejin,
    "kaopu": fetch_kaopu,
    "kuaishou": fetch_kuaishou,
    "nowcoder": fetch_nowcoder,
    "pcbeta": fetch_pcbeta_windows11,
    "pcbeta-windows11": fetch_pcbeta_windows11,
    "producthunt": fetch_producthunt,
    "qqvideo": fetch_qqvideo_hotsearch,
    "qqvideo-tv-hotsearch": fetch_qqvideo_hotsearch,
    "solidot": fetch_solidot,
    "sputniknewscn": fetch_sputniknewscn,
    "sspai": fetch_sspai,
    "tencent": fetch_tencent_hot,
    "tencent-hot": fetch_tencent_hot,
    "thepaper": fetch_thepaper,
    "tieba": fetch_tieba,
    "toutiao": fetch_toutiao,
    "wallstreetcn": fetch_wallstreetcn_quick,
    "wallstreetcn-hot": fetch_wallstreetcn_hot,
    "wallstreetcn-news": fetch_wallstreetcn_news,
    "wallstreetcn-quick": fetch_wallstreetcn_quick,
    "weibo": fetch_weibo,
    "xueqiu": fetch_xueqiu_hotstock,
    "xueqiu-hotstock": fetch_xueqiu_hotstock,
    "zhihu": fetch_zhihu,
}




def get_source_handler(source_id: str) -> SourceHandler:
    return SOURCE_REGISTRY[source_id]
