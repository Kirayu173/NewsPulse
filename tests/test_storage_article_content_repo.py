import unittest

from newspulse.storage import ArticleContentRecord, SQLiteRuntime
from newspulse.storage.repos import ArticleContentRepository
from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory


class ArticleContentRepositoryTest(unittest.TestCase):
    def test_save_and_load_cached_article_content(self):
        with TemporaryDirectory() as tmp:
            runtime = SQLiteRuntime(data_dir=tmp, timezone='Asia/Shanghai')
            repo = ArticleContentRepository(runtime)
            record = ArticleContentRecord(
                normalized_url='https://example.com/post',
                source_type='article',
                source_id='thepaper',
                source_name='婢庢箖鏂伴椈',
                source_kind='article',
                original_url='https://example.com/post?utm_source=x',
                final_url='https://example.com/post',
                title='Example title',
                excerpt='Example excerpt',
                content_text='Long body',
                content_markdown='Long body',
                content_hash='abc123',
                extractor_name='readability',
                fetch_status='ok',
                trace={'cache_hit': False},
            )

            self.assertTrue(repo._save_impl(record))
            loaded = repo._get_by_normalized_url_impl('https://example.com/post')

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.title, 'Example title')
            self.assertEqual(loaded.fetch_status, 'ok')
            self.assertEqual(loaded.trace['cache_hit'], False)
            runtime.close_all()


if __name__ == '__main__':
    unittest.main()
