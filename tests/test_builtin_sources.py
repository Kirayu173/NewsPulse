import os
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from newspulse.crawler import CrawlSourceSpec, DataFetcher
from newspulse.crawler.models import SourceDefinition
from newspulse.crawler.sources import registry as source_registry
from newspulse.crawler.sources.base import SourceItem
from newspulse.crawler.sources.builtin import (
    SOURCE_DEFINITIONS,
    SOURCE_REGISTRY,
    fetch_coolapk,
    fetch_github_trending,
    fetch_hackernews,
    fetch_producthunt,
    resolve_source_definition,
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

    def test_registry_resolves_alias_to_structured_definition(self):
        definition = resolve_source_definition("github")

        self.assertEqual(definition.canonical_id, "github-trending-today")
        self.assertEqual(definition.category, "tech")
        self.assertIs(SOURCE_DEFINITIONS["github-trending-today"], definition)

    def test_fetcher_returns_native_batch_contract(self):
        def fake_source(_client):
            return [
                SourceItem(title="Alpha", url="https://example.com/a"),
                SourceItem(title="Alpha", url="https://example.com/a2"),
                SourceItem(title="Beta", url="https://example.com/b", mobile_url="https://m.example.com/b"),
            ]

        with patch.dict(SOURCE_REGISTRY, {"unit-test-source": fake_source}, clear=False):
            source_definition = SourceDefinition(
                canonical_id="unit-test-source",
                handler=fake_source,
                default_name="Unit Test",
                category="test",
            )
            with patch.dict(
                source_registry.SOURCE_DEFINITIONS,
                {"unit-test-source": source_definition},
                clear=False,
            ), patch.dict(
                source_registry.SOURCE_ALIAS_INDEX,
                {"unit-test-source": source_definition},
                clear=False,
            ):
                fetcher = DataFetcher()
                batch = fetcher.crawl(
                    [CrawlSourceSpec(source_id="unit-test-source", source_name="Unit Test")],
                    request_interval=0,
                )

        self.assertEqual(batch.successful_source_ids, ["unit-test-source"])
        self.assertEqual(batch.failed_source_ids, [])
        self.assertEqual(batch.platform_names["unit-test-source"], "Unit Test")
        self.assertEqual([item.title for item in batch.sources[0].items], ["Alpha", "Alpha", "Beta"])
        self.assertEqual(batch.sources[0].items[2].mobile_url, "https://m.example.com/b")

    def test_fetcher_falls_back_to_registry_default_name_when_config_name_is_placeholder(self):
        def fake_source(_client):
            return [SourceItem(title="Alpha", url="https://example.com/a")]

        with patch.dict(SOURCE_REGISTRY, {"unit-test-source": fake_source}, clear=False):
            source_definition = SourceDefinition(
                canonical_id="unit-test-source",
                handler=fake_source,
                default_name="\u5355\u5143\u6d4b\u8bd5\u6e90",
                category="test",
            )
            with patch.dict(
                source_registry.SOURCE_DEFINITIONS,
                {"unit-test-source": source_definition},
                clear=False,
            ), patch.dict(
                source_registry.SOURCE_ALIAS_INDEX,
                {"unit-test-source": source_definition},
                clear=False,
            ):
                fetcher = DataFetcher()
                batch = fetcher.crawl(
                    [CrawlSourceSpec(source_id="unit-test-source", source_name="??")],
                    request_interval=0,
                )

        self.assertEqual(batch.platform_names["unit-test-source"], "\u5355\u5143\u6d4b\u8bd5\u6e90")

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

    def test_fetch_github_trending_falls_back_to_search_api_when_html_unavailable(self):
        class FakeResponse:
            def json(self):
                return {
                    "items": [
                        {
                            "full_name": "openai/openai-agents-python",
                            "html_url": "https://github.com/openai/openai-agents-python",
                            "description": "Official OpenAI Agents SDK for Python",
                            "language": "Python",
                            "stargazers_count": 12345,
                            "forks_count": 321,
                        },
                        {
                            "full_name": "deepseek-ai/DeepGEMM",
                            "html_url": "https://github.com/deepseek-ai/DeepGEMM",
                            "description": "FP8 GEMM kernels",
                            "language": "CUDA",
                            "stargazers_count": 4567,
                            "forks_count": 89,
                        },
                    ]
                }

        class FakeClient:
            def __init__(self):
                self.request_calls = []

            def get_soup(self, _url, **_kwargs):
                raise RuntimeError("timeout")

            def request(self, method, url, **kwargs):
                self.request_calls.append((method, url, kwargs))
                return FakeResponse()

        client = FakeClient()
        items = fetch_github_trending(client)

        self.assertEqual(
            [item.title for item in items],
            ["openai/openai-agents-python", "deepseek-ai/DeepGEMM"],
        )
        self.assertEqual(
            [item.url for item in items],
            [
                "https://github.com/openai/openai-agents-python",
                "https://github.com/deepseek-ai/DeepGEMM",
            ],
        )
        self.assertEqual(items[0].summary, "Official OpenAI Agents SDK for Python")
        self.assertEqual(items[0].metadata["source_kind"], "github_repository")
        self.assertEqual(items[0].metadata["github"]["language"], "Python")
        self.assertEqual(items[0].metadata["github"]["source_variant"], "search_api_fallback")
        self.assertEqual(client.request_calls[0][0], "GET")
        self.assertEqual(client.request_calls[0][1], "https://api.github.com/search/repositories")

    def test_fetch_github_trending_html_extracts_structured_context(self):
        class FakeClient:
            def get_soup(self, _url, **_kwargs):
                html = """
                <main>
                  <article class="Box-row">
                    <h2 class="h3 lh-condensed">
                      <a href="/openai/openai-agents-python">
                        openai / openai-agents-python
                      </a>
                    </h2>
                    <p>Official OpenAI Agents SDK for Python</p>
                    <div>
                      <span itemprop="programmingLanguage">Python</span>
                      <a href="/openai/openai-agents-python/stargazers">12,345</a>
                      <a href="/openai/openai-agents-python/forks">678</a>
                      <span>842 stars today</span>
                    </div>
                  </article>
                </main>
                """
                return BeautifulSoup(html, "html.parser")

        with patch.dict(os.environ, {"GITHUB_TOKEN": "", "GITHUB_API_TOKEN": ""}, clear=False):
            items = fetch_github_trending(FakeClient())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "openai/openai-agents-python")
        self.assertEqual(items[0].summary, "Official OpenAI Agents SDK for Python")
        self.assertEqual(items[0].metadata["source_context_version"], 1)
        self.assertEqual(items[0].metadata["github"]["language"], "Python")
        self.assertEqual(items[0].metadata["github"]["stars_today"], 842)
        self.assertEqual(items[0].metadata["github"]["stars_total"], 12345)
        self.assertEqual(items[0].metadata["github"]["forks_total"], 678)
        self.assertEqual(items[0].metadata["github"]["enriched_by"], "html")

    def test_fetch_github_trending_enriches_html_items_with_repo_api(self):
        class FakeClient:
            def __init__(self):
                self.json_calls = []

            def get_soup(self, _url, **_kwargs):
                html = """
                <main>
                  <article class="Box-row">
                    <h2><a href="/openai/openai-agents-python">openai / openai-agents-python</a></h2>
                    <p>Official OpenAI Agents SDK for Python</p>
                    <div>
                      <span itemprop="programmingLanguage">Python</span>
                      <a href="/openai/openai-agents-python/stargazers">12,345</a>
                      <a href="/openai/openai-agents-python/forks">678</a>
                      <span>842 stars today</span>
                    </div>
                  </article>
                </main>
                """
                return BeautifulSoup(html, "html.parser")

            def get_json(self, url, **kwargs):
                self.json_calls.append((url, kwargs))
                return {
                    "full_name": "openai/openai-agents-python",
                    "description": "Official OpenAI Agents SDK for Python",
                    "language": "Python",
                    "topics": ["openai", "agent", "sdk"],
                    "stargazers_count": 15000,
                    "forks_count": 900,
                    "created_at": "2024-08-06T00:00:00Z",
                    "pushed_at": "2026-04-19T00:00:00Z",
                    "archived": False,
                    "fork": False,
                }

        client = FakeClient()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "unit-test-token", "GITHUB_API_TOKEN": ""}, clear=False):
            items = fetch_github_trending(client)

        self.assertEqual(len(items), 1)
        self.assertEqual(client.json_calls[0][0], "https://api.github.com/repos/openai/openai-agents-python")
        self.assertEqual(items[0].metadata["github"]["topics"], ["openai", "agent", "sdk"])
        self.assertEqual(items[0].metadata["github"]["stars_total"], 15000)
        self.assertEqual(items[0].metadata["github"]["pushed_at"], "2026-04-19T00:00:00Z")
        self.assertEqual(items[0].metadata["github"]["enriched_by"], "html+api")


if __name__ == "__main__":
    unittest.main()
