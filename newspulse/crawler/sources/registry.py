# coding=utf-8
"""Registry for builtin hotlist handlers."""

from __future__ import annotations

from newspulse.crawler.models import SourceDefinition, SourceHandler
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


def _definition(
    canonical_id: str,
    handler: SourceHandler,
    *,
    aliases: tuple[str, ...] = (),
    category: str,
    default_name: str = "",
) -> SourceDefinition:
    return SourceDefinition(
        canonical_id=canonical_id,
        handler=handler,
        default_name=default_name or canonical_id,
        category=category,
        aliases=aliases,
    )


SOURCE_DEFINITIONS: dict[str, SourceDefinition] = {
    "36kr-quick": _definition("36kr-quick", fetch_36kr_quick, aliases=("36kr",), category="mainland"),
    "baidu": _definition("baidu", fetch_baidu, category="mainland"),
    "bilibili-hot-search": _definition(
        "bilibili-hot-search",
        fetch_bilibili_hot_search,
        aliases=("bilibili",),
        category="mainland",
    ),
    "bilibili-hot-video": _definition("bilibili-hot-video", fetch_bilibili_hot_video, category="mainland"),
    "bilibili-ranking": _definition("bilibili-ranking", fetch_bilibili_ranking, category="mainland"),
    "cankaoxiaoxi": _definition("cankaoxiaoxi", fetch_cankaoxiaoxi, category="misc"),
    "chongbuluo-hot": _definition(
        "chongbuluo-hot",
        fetch_chongbuluo_hot,
        aliases=("chongbuluo",),
        category="tech",
    ),
    "chongbuluo-latest": _definition("chongbuluo-latest", fetch_chongbuluo_latest, category="tech"),
    "cls-depth": _definition("cls-depth", fetch_cls_depth, category="finance"),
    "cls-hot": _definition(
        "cls-hot",
        fetch_cls_hot,
        category="finance",
        default_name="\u8d22\u8054\u793e\u70ed\u699c",
    ),
    "cls-telegraph": _definition("cls-telegraph", fetch_cls_telegraph, aliases=("cls",), category="finance"),
    "coolapk": _definition("coolapk", fetch_coolapk, category="tech"),
    "douban": _definition("douban", fetch_douban, category="mainland"),
    "douyin": _definition("douyin", fetch_douyin, category="mainland"),
    "gelonghui": _definition("gelonghui", fetch_gelonghui, category="finance"),
    "github-trending-today": _definition(
        "github-trending-today",
        fetch_github_trending,
        aliases=("github",),
        category="tech",
        default_name="GitHub Trending",
    ),
    "ghxi": _definition("ghxi", fetch_ghxi, category="tech"),
    "hackernews": _definition("hackernews", fetch_hackernews, category="tech", default_name="Hacker News"),
    "hupu": _definition("hupu", fetch_hupu, category="misc"),
    "ifeng": _definition("ifeng", fetch_ifeng, category="mainland"),
    "iqiyi-hot-ranklist": _definition(
        "iqiyi-hot-ranklist",
        fetch_iqiyi_hot_ranklist,
        aliases=("iqiyi",),
        category="mainland",
    ),
    "ithome": _definition("ithome", fetch_ithome, category="tech"),
    "jin10": _definition("jin10", fetch_jin10, category="finance"),
    "juejin": _definition(
        "juejin",
        fetch_juejin,
        category="tech",
        default_name="\u7a00\u571f",
    ),
    "kaopu": _definition("kaopu", fetch_kaopu, category="tech"),
    "kuaishou": _definition("kuaishou", fetch_kuaishou, category="mainland"),
    "nowcoder": _definition("nowcoder", fetch_nowcoder, category="tech"),
    "pcbeta-windows11": _definition(
        "pcbeta-windows11",
        fetch_pcbeta_windows11,
        aliases=("pcbeta",),
        category="tech",
    ),
    "producthunt": _definition("producthunt", fetch_producthunt, category="tech"),
    "qqvideo-tv-hotsearch": _definition(
        "qqvideo-tv-hotsearch",
        fetch_qqvideo_hotsearch,
        aliases=("qqvideo",),
        category="mainland",
    ),
    "solidot": _definition("solidot", fetch_solidot, category="tech"),
    "sputniknewscn": _definition("sputniknewscn", fetch_sputniknewscn, category="misc"),
    "sspai": _definition("sspai", fetch_sspai, category="tech"),
    "tencent-hot": _definition(
        "tencent-hot",
        fetch_tencent_hot,
        aliases=("tencent",),
        category="mainland",
        default_name="\u817e\u8baf\u70ed\u699c",
    ),
    "thepaper": _definition(
        "thepaper",
        fetch_thepaper,
        category="mainland",
        default_name="\u6f8e\u6e43\u65b0\u95fb",
    ),
    "tieba": _definition("tieba", fetch_tieba, category="mainland"),
    "toutiao": _definition("toutiao", fetch_toutiao, category="mainland"),
    "wallstreetcn-hot": _definition(
        "wallstreetcn-hot",
        fetch_wallstreetcn_hot,
        category="finance",
        default_name="\u534e\u5c14\u8857\u89c1\u95fb\u70ed\u699c",
    ),
    "wallstreetcn-news": _definition("wallstreetcn-news", fetch_wallstreetcn_news, category="finance"),
    "wallstreetcn-quick": _definition(
        "wallstreetcn-quick",
        fetch_wallstreetcn_quick,
        aliases=("wallstreetcn",),
        category="finance",
    ),
    "weibo": _definition("weibo", fetch_weibo, category="mainland"),
    "xueqiu-hotstock": _definition(
        "xueqiu-hotstock",
        fetch_xueqiu_hotstock,
        aliases=("xueqiu",),
        category="finance",
    ),
    "zhihu": _definition("zhihu", fetch_zhihu, category="mainland"),
}

SOURCE_ALIAS_INDEX: dict[str, SourceDefinition] = {}
SOURCE_REGISTRY: dict[str, SourceHandler] = {}

for definition in SOURCE_DEFINITIONS.values():
    keys = (definition.canonical_id, *definition.aliases)
    for key in keys:
        SOURCE_ALIAS_INDEX[key] = definition
        SOURCE_REGISTRY[key] = definition.handler


def resolve_source_definition(source_id: str) -> SourceDefinition:
    return SOURCE_ALIAS_INDEX[source_id]


def get_source_handler(source_id: str) -> SourceHandler:
    return resolve_source_definition(source_id).handler
