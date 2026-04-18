import os
import unittest
from unittest.mock import patch

from newspulse.crawler.fetcher import DataFetcher
from newspulse.crawler.sources.base import SourceItem
from newspulse.crawler.sources.builtin import (
    SOURCE_REGISTRY,
    fetch_coolapk,
    fetch_hackernews,
    fetch_producthunt,
)


EXPECTED_SOURCE_IDS = {
    "36kr",
    "36kr-quick",
    "baidu",
    "bilibili",
    "bilibili-hot-search",
    "bilibili-hot-video",
    "bilibili-ranking",
    "cankaoxiaoxi",
    "chongbuluo",
    "chongbuluo-hot",
    "chongbuluo-latest",
    "cls",
    "cls-depth",
    "cls-hot",
    "cls-telegraph",
    "coolapk",
    "douban",
    "douyin",
    "gelonghui",
    "github",
    "github-trending-today",
    "ghxi",
    "hackernews",
    "hupu",
    "ifeng",
    "iqiyi",
    "iqiyi-hot-ranklist",
    "ithome",
    "jin10",
    "juejin",
    "kaopu",
    "kuaishou",
    "nowcoder",
    "pcbeta",
    "pcbeta-windows11",
    "producthunt",
    "qqvideo",
    "qqvideo-tv-hotsearch",
    "solidot",
    "sputniknewscn",
    "sspai",
    "tencent",
    "tencent-hot",
    "thepaper",
    "tieba",
    "toutiao",
    "wallstreetcn",
    "wallstreetcn-hot",
    "wallstreetcn-news",
    "wallstreetcn-quick",
    "weibo",
    "xueqiu",
    "xueqiu-hotstock",
    "zhihu",
}


class BuiltinSourceRegistryTest(unittest.TestCase):
    def test_registry_covers_expected_source_ids(self):
        self.assertEqual(set(SOURCE_REGISTRY), EXPECTED_SOURCE_IDS)

    def test_fetcher_keeps_old_result_shape(self):
        def fake_source(_client):
            return [
                SourceItem(title="Alpha", url="https://example.com/a"),
                SourceItem(title="Alpha", url="https://example.com/a2"),
                SourceItem(title="Beta", url="https://example.com/b", mobile_url="https://m.example.com/b"),
            ]

        with patch.dict(SOURCE_REGISTRY, {"unit-test-source": fake_source}, clear=False):
            fetcher = DataFetcher()
            results, id_to_name, failed_ids = fetcher.crawl_websites(
                [("unit-test-source", "Unit Test")],
                request_interval=0,
            )

        self.assertEqual(id_to_name["unit-test-source"], "Unit Test")
        self.assertEqual(failed_ids, [])
        self.assertEqual(results["unit-test-source"]["Alpha"]["ranks"], [1, 2])
        self.assertEqual(
            results["unit-test-source"]["Beta"]["mobileUrl"],
            "https://m.example.com/b",
        )

    def test_fetch_coolapk_skips_empty_message_rows(self):
        class FakeClient:
            def get_json(self, _url, **_kwargs):
                return {
                    "data": [
                        {
                            "id": 1,
                            "editor_title": "",
                            "message": "",
                            "url": "/feed/1",
                        },
                        {
                            "id": 2,
                            "editor_title": "",
                            "message": "<p>Second item</p>",
                            "url": "/feed/2",
                        },
                    ]
                }

        items = fetch_coolapk(FakeClient())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Second item")
        self.assertEqual(items[0].url, "https://www.coolapk.com/feed/2")

    def test_fetch_producthunt_uses_public_feed_when_token_missing(self):
        class FakeFeed:
            entries = [
                {
                    "title": "Launch One",
                    "link": "https://www.producthunt.com/products/launch-one",
                }
            ]

        class FakeClient:
            def get_feed(self, _url, **_kwargs):
                return FakeFeed()

        with patch.dict(os.environ, {"PRODUCTHUNT_API_TOKEN": ""}, clear=False):
            items = fetch_producthunt(FakeClient())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Launch One")
        self.assertEqual(
            items[0].url,
            "https://www.producthunt.com/products/launch-one",
        )

    def test_fetch_hackernews_uses_hn_aimaker_page(self):
        class FakeClient:
            def get_soup(self, _url, **_kwargs):
                from bs4 import BeautifulSoup

                html = """
                <div>
                  <article>
                    <div class="flex items-start gap-2">
                      <a href="https://example.com/story">Translated Story</a>
                    </div>
                    <div>
                      <a href="https://news.ycombinator.com/item?id=123">原帖</a>
                    </div>
                  </article>
                  <article>
                    <div class="flex items-start gap-2">
                      <a href="/item/456">Ask HN Local</a>
                    </div>
                  </article>
                </div>
                """
                return BeautifulSoup(html, "html.parser")

        items = fetch_hackernews(FakeClient())

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Translated Story")
        self.assertEqual(items[0].url, "https://news.ycombinator.com/item?id=123")
        self.assertEqual(items[0].mobile_url, "https://example.com/story")
        self.assertEqual(items[1].url, "https://hn.aimaker.dev/item/456")


if __name__ == "__main__":
    unittest.main()
