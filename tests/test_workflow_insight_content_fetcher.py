import json
import unittest
from tempfile import TemporaryDirectory

from newspulse.storage import get_storage_manager
from newspulse.workflow.insight.content_fetcher import InsightContentFetcher
from newspulse.workflow.insight.input_builder import InsightInputBuilder
from newspulse.workflow.insight.models import ExtractedContent, InsightContentPayload, InsightNewsContext, InsightRankSignals, InsightSelectionEvidence, InsightSourceContext


class FakeExtractor:
    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = 0

    def extract(self, *, url, html):
        self.calls += 1
        value = self.result(url, html) if callable(self.result) else self.result
        return value


class FakeResponse:
    def __init__(self, url, text, status_code=200):
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'http {self.status_code}')

    def json(self):
        return json.loads(self.text)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.headers = {}
        self.proxies = {}

    def get(self, url, timeout=0, headers=None):
        self.calls.append(url)
        response = self.responses[url]
        return response


class AsyncStubFetcher(InsightContentFetcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.async_calls = []

    def _fetch_many_async(self, contexts):
        self.async_calls.append([context.news_item_id for context in contexts])
        return [
            InsightContentPayload(
                news_item_id=context.news_item_id,
                status='ok',
                source_type=context.source_context.source_kind or 'article',
                content_text='异步正文' * 40,
                content_markdown='异步正文' * 40,
                trace={'cache_hit': False, 'mode': 'async'},
            )
            for context in contexts
        ]


class InsightContentFetcherTest(unittest.TestCase):
    def _context(self, **kwargs):
        return InsightNewsContext(
            news_item_id=kwargs.get('news_item_id', '1'),
            title=kwargs.get('title', 'Example title'),
            source_id=kwargs.get('source_id', 'thepaper'),
            source_name=kwargs.get('source_name', '澎湃新闻'),
            url=kwargs.get('url', 'https://example.com/post'),
            rank_signals=InsightRankSignals(current_rank=1),
            source_context=kwargs.get(
                'source_context',
                InsightSourceContext(source_kind=kwargs.get('source_kind', 'article'), summary='Example summary'),
            ),
            selection_evidence=kwargs.get(
                'selection_evidence',
                InsightSelectionEvidence(matched_topics=('AI',), llm_reasons=('高价值',), quality_score=0.9),
            ),
        )

    def test_article_route_uses_extractor_fallback_and_then_hits_cache(self):
        with TemporaryDirectory() as tmp:
            storage = get_storage_manager(
                backend_type='local',
                data_dir=tmp,
                enable_txt=False,
                enable_html=False,
                timezone='Asia/Shanghai',
            )
            empty = FakeExtractor('empty', ExtractedContent(success=False, extractor_name='empty', error_type='empty', error_message='no text'))
            success = FakeExtractor(
                'success',
                ExtractedContent(
                    success=True,
                    title='Extracted title',
                    excerpt='Extracted excerpt',
                    text='这是一段足够长的正文内容。' * 20,
                    markdown='这是一段足够长的正文内容。' * 20,
                    final_url='https://example.com/post',
                    extractor_name='success',
                ),
            )
            session = FakeSession({'https://example.com/post': FakeResponse('https://example.com/post', '<html></html>')})
            fetcher = InsightContentFetcher(
                storage_manager=storage,
                extractors=[empty, success],
                session=session,
            )
            context = self._context()

            first = fetcher.fetch_one(context)
            second = fetcher.fetch_one(context)

            self.assertEqual(first.status, 'ok')
            self.assertEqual(first.extractor_name, 'success')
            self.assertFalse(first.trace['cache_hit'])
            self.assertTrue(second.trace['cache_hit'])
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(empty.calls, 1)
            self.assertEqual(success.calls, 1)
            storage.cleanup()

    def test_hackernews_route_prefers_external_link(self):
        with TemporaryDirectory() as tmp:
            storage = get_storage_manager(
                backend_type='local',
                data_dir=tmp,
                enable_txt=False,
                enable_html=False,
                timezone='Asia/Shanghai',
            )
            extractor = FakeExtractor(
                'success',
                ExtractedContent(
                    success=True,
                    title='External article',
                    excerpt='External excerpt',
                    text='外链正文内容。' * 30,
                    markdown='外链正文内容。' * 30,
                    final_url='https://external.example.com/a',
                    extractor_name='success',
                ),
            )
            session = FakeSession(
                {
                    'https://news.ycombinator.com/item?id=1': FakeResponse(
                        'https://news.ycombinator.com/item?id=1',
                        '<html><body><span class="titleline"><a href="https://external.example.com/a">story</a></span></body></html>',
                    ),
                    'https://external.example.com/a': FakeResponse('https://external.example.com/a', '<html></html>'),
                }
            )
            fetcher = InsightContentFetcher(storage_manager=storage, extractors=[extractor], session=session)
            context = self._context(source_id='hackernews', source_name='Hacker News', source_kind='hackernews_item', url='https://news.ycombinator.com/item?id=1')

            payload = fetcher.fetch_one(context)

            self.assertEqual(payload.source_type, 'hackernews_external')
            self.assertEqual(payload.status, 'ok')
            self.assertEqual(payload.trace['route'], 'external_link')
            storage.cleanup()

    def test_github_route_builds_repo_context_without_article_fetch(self):
        with TemporaryDirectory() as tmp:
            storage = get_storage_manager(
                backend_type='local',
                data_dir=tmp,
                enable_txt=False,
                enable_html=False,
                timezone='Asia/Shanghai',
            )
            session = FakeSession(
                {
                    'https://api.github.com/repos/openai/codex/readme': FakeResponse(
                        'https://api.github.com/repos/openai/codex/readme',
                        'README content ' * 40,
                    ),
                    'https://api.github.com/repos/openai/codex/releases/latest': FakeResponse(
                        'https://api.github.com/repos/openai/codex/releases/latest',
                        '{"name": "v1.0.0", "body": "Release notes"}',
                    ),
                }
            )
            context = self._context(
                source_id='github-trending-today',
                source_name='GitHub Trending',
                url='https://github.com/openai/codex',
                source_context=InsightSourceContext(
                    source_kind='github_repository',
                    summary='A coding agent for software tasks.',
                    metadata={'full_name': 'openai/codex', 'description': 'A coding agent for software tasks.', 'language': 'Python', 'topics': ['agent']},
                ),
            )
            fetcher = InsightContentFetcher(storage_manager=storage, session=session)

            payload = fetcher.fetch_one(context)

            self.assertEqual(payload.status, 'repo_context')
            self.assertEqual(payload.source_type, 'github_repository')
            self.assertIn('Repository: openai/codex', payload.content_text)
            self.assertIn('README:', payload.content_text)
            storage.cleanup()

    def test_fetch_many_uses_async_runner_when_enabled(self):
        fetcher = AsyncStubFetcher(
            async_enabled=True,
            max_concurrency=4,
            request_timeout=9,
        )
        contexts = [
            self._context(news_item_id='1', url='https://example.com/a'),
            self._context(news_item_id='2', url='https://example.com/b'),
        ]

        payloads = fetcher.fetch_many(contexts)

        self.assertEqual(fetcher.async_calls, [['1', '2']])
        self.assertEqual([payload.news_item_id for payload in payloads], ['1', '2'])
        self.assertEqual(payloads[0].trace['mode'], 'async')


if __name__ == '__main__':
    unittest.main()
