# Source Config Status

Last updated: 2026-04-16

This document records the current source configuration after the project was simplified to hotlist-only mode.

## Runtime Summary

- Source type: hotlist only
- Enabled sources in `config/config.yaml`: 12
- Builtin source ids in registry: 54
- Builtin actual sources after alias dedupe: 43
- Current report mode: `current`
- Current display mode: `keyword`
- Display regions:
  - `hotlist`: enabled
  - `new_items`: disabled
  - `standalone`: disabled
  - `ai_analysis`: enabled
- Standalone source list:
  - `wallstreetcn-hot`

## Enabled Sources

Below is the current enabled set in `config/config.yaml`, grouped by domain.
When a source has a compatibility alias, it is shown in parentheses.

### General / News / Social

- `thepaper` - 澎湃新闻
- `tencent-hot` (`tencent`) - 腾讯新闻
- `toutiao` - 今日头条

### Finance / Markets

- `wallstreetcn-hot` - 华尔街见闻
- `cls-hot` - 财联社热门

### Tech / Developer / Product

- `github-trending-today` (`github`) - GitHub Trending
- `hackernews` - Hacker News
- `juejin` - 掘金
- `producthunt` - Product Hunt
- `coolapk` - 酷安
- `chongbuluo-hot` (`chongbuluo`) - 虫部落热榜
- `ithome` - IT之家

## Available But Disabled Sources

These sources exist in the builtin registry but are not enabled in the current config.
They are also grouped by domain and deduped by actual handler.

### General / News / Social

- `36kr-quick` (`36kr`) - 36氪快讯
- `baidu` - 百度热搜
- `bilibili-hot-search` (`bilibili`) - bilibili 热搜
- `bilibili-hot-video` - bilibili 热门视频
- `bilibili-ranking` - bilibili 排行榜
- `douban` - 豆瓣
- `douyin` - 抖音
- `ifeng` - 凤凰网
- `iqiyi-hot-ranklist` (`iqiyi`) - 爱奇艺热搜
- `kuaishou` - 快手
- `qqvideo-tv-hotsearch` (`qqvideo`) - 腾讯视频热搜
- `tieba` - 贴吧
- `weibo` - 微博
- `zhihu` - 知乎

### Finance / Markets

- `cls-telegraph` (`cls`) - 财联社电报
- `cls-depth` - 财联社深度
- `gelonghui` - 格隆汇
- `jin10` - 金十
- `wallstreetcn-quick` (`wallstreetcn`) - 华尔街见闻快讯
- `wallstreetcn-news` - 华尔街见闻新闻
- `xueqiu-hotstock` (`xueqiu`) - 雪球热股

### Tech / Developer / Product

- `chongbuluo-latest` - 虫部落最新
- `ghxi` - 果核剥壳
- `kaopu` - 靠谱AI
- `nowcoder` - 牛客
- `pcbeta-windows11` (`pcbeta`) - PCBeta Windows 11
- `solidot` - Solidot
- `sspai` - 少数派

### Other / International / Sports

- `cankaoxiaoxi` - 参考消息
- `hupu` - 虎扑
- `sputniknewscn` - 卫星通讯社中文

## Live Fetch Verification

Verification method:

- Use the real builtin handlers through `DataFetcher.fetch_data()`
- Test against the currently enabled 12 sources
- Use the live network at verification time
- Verification date: 2026-04-16

### Result Summary

- Total tested: 12
- Success: 12
- Failed: 0
- Conclusion: the current enabled source set can fetch real news successfully

### Per-Source Result

| Source ID | Name | Domain | Status | Items |
| --- | --- | --- | --- | ---: |
| `thepaper` | 澎湃新闻 | General | OK | 20 |
| `wallstreetcn-hot` | 华尔街见闻 | Finance | OK | 10 |
| `cls-hot` | 财联社热门 | Finance | OK | 13 |
| `tencent-hot` | 腾讯新闻 | General | OK | 15 |
| `github-trending-today` | GitHub Trending | Tech | OK | 13 |
| `hackernews` | Hacker News | Tech | OK | 20 |
| `juejin` | 掘金 | Tech | OK | 50 |
| `producthunt` | Product Hunt | Tech | OK | 50 |
| `coolapk` | 酷安 | Tech | OK | 17 |
| `chongbuluo-hot` | 虫部落热榜 | Tech | OK | 27 |
| `ithome` | IT之家 | Tech | OK | 43 |
| `toutiao` | 今日头条 | General | OK | 50 |

## Notes

- Registry counts include compatibility aliases such as `github` -> `github-trending-today`.
- The current config deliberately favors:
  - broad public news
  - finance / market pulse
  - developer / product / tech community sources
- `display.standalone.platforms` still includes `wallstreetcn-hot`, but the standalone region itself is currently disabled in `config/config.yaml`.
