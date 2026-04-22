import shutil
import sqlite3
import unittest
import uuid
from pathlib import Path

from newspulse.crawler import CrawlBatchResult, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import StorageManager, normalize_crawl_batch
from newspulse.storage.sqlite_runtime import SQLiteRuntime


class StorageStage2Test(unittest.TestCase):
    def _create_workspace_tmpdir(self) -> Path:
        root = Path('.tmp-test') / 'storage-stage2'
        root.mkdir(parents=True, exist_ok=True)
        path = root / str(uuid.uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def _create_storage(self, tmp_path: Path) -> StorageManager:
        return StorageManager(
            backend_type='local',
            data_dir=str(tmp_path / 'output'),
            enable_txt=False,
            enable_html=False,
        )

    def test_normalize_crawl_batch_returns_native_stage2_contract(self):
        batch = normalize_crawl_batch(
            crawl_batch=CrawlBatchResult(
                sources=[
                    SourceFetchResult(
                        source_id='s1',
                        source_name='平台1',
                        resolved_source_id='s1',
                        items=[
                            SourceItem(
                                title='Alpha',
                                url='https://example.com/a',
                                summary='Alpha summary',
                                metadata={'source_kind': 'generic', 'tags': ['alpha']},
                            ),
                            SourceItem(title='Alpha', url='https://example.com/a2'),
                            SourceItem(title='Beta', url='https://example.com/b'),
                        ],
                    )
                ],
                failures=[
                    SourceFetchFailure(
                        source_id='s2',
                        source_name='平台2',
                        resolved_source_id='s2',
                        exception_type='TimeoutError',
                        message='timeout',
                        attempts=3,
                        retryable=True,
                    )
                ],
            ),
            crawl_time='2026-04-18 10:00:00',
            crawl_date='2026-04-18',
        )

        self.assertEqual(batch.id_to_name['s1'], '平台1')
        self.assertEqual(batch.id_to_name['s2'], '平台2')
        self.assertEqual(batch.failed_ids, ['s2'])
        alpha = next(item for item in batch.items['s1'] if item.title == 'Alpha')
        self.assertEqual(alpha.ranks, [1, 2])
        self.assertEqual(alpha.summary, 'Alpha summary')
        self.assertEqual(alpha.metadata['tags'], ['alpha'])
        self.assertEqual(batch.failures[0].exception_type, 'TimeoutError')
        self.assertEqual(batch.failures[0].message, 'timeout')

    def test_storage_persists_structured_failure_details(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            first_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id='s1',
                            source_name='平台1',
                            resolved_source_id='s1',
                            items=[
                                SourceItem(
                                    title='Alpha',
                                    url='https://example.com/a',
                                    summary='Official OpenAI Agents SDK for Python',
                                    metadata={
                                        'source_context_version': 1,
                                        'source_kind': 'github_repository',
                                        'github': {
                                            'full_name': 'openai/openai-agents-python',
                                            'language': 'Python',
                                            'topics': ['openai', 'agent', 'sdk'],
                                        },
                                    },
                                )
                            ],
                        )
                    ],
                    failures=[],
                ),
                crawl_time='2026-04-18 09:00:00',
                crawl_date='2026-04-18',
            )
            second_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id='s1',
                            source_name='平台1',
                            resolved_source_id='s1',
                            items=[SourceItem(title='Alpha', url='https://example.com/a')],
                        )
                    ],
                    failures=[
                        SourceFetchFailure(
                            source_id='s2',
                            source_name='平台2',
                            resolved_source_id='s2',
                            exception_type='ConnectionError',
                            message='boom',
                            attempts=2,
                            retryable=False,
                        )
                    ],
                ),
                crawl_time='2026-04-18 10:00:00',
                crawl_date='2026-04-18',
            )

            self.assertTrue(storage.save_normalized_crawl_batch(first_batch))
            self.assertTrue(storage.save_normalized_crawl_batch(second_batch))

            latest = storage.get_latest_crawl_data()
            all_data = storage.get_today_all_data()
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIsNotNone(latest)
        self.assertIsNotNone(all_data)
        assert latest is not None
        assert all_data is not None
        self.assertEqual(latest.failed_ids, ['s2'])
        self.assertEqual(latest.failures[0].source_name, '平台2')
        self.assertEqual(latest.failures[0].exception_type, 'ConnectionError')
        self.assertEqual(latest.failures[0].message, 'boom')
        self.assertEqual(latest.failures[0].attempts, 2)
        self.assertEqual(all_data.failures[0].source_id, 's2')
        self.assertEqual(all_data.items['s1'][0].ranks, [1])
        self.assertEqual(latest.items['s1'][0].summary, 'Official OpenAI Agents SDK for Python')
        self.assertEqual(latest.items['s1'][0].metadata['github']['topics'], ['openai', 'agent', 'sdk'])

    def test_storage_tracks_title_changes_and_off_list_entries(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            first_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id='s1',
                            source_name='平台1',
                            resolved_source_id='s1',
                            items=[
                                SourceItem(title='Alpha', url='https://example.com/a', summary='alpha'),
                                SourceItem(title='Beta', url='https://example.com/b'),
                            ],
                        )
                    ],
                    failures=[],
                ),
                crawl_time='2026-04-18 09:00:00',
                crawl_date='2026-04-18',
            )
            second_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[
                        SourceFetchResult(
                            source_id='s1',
                            source_name='平台1',
                            resolved_source_id='s1',
                            items=[
                                SourceItem(title='Alpha v2', url='https://example.com/a?utm_source=test'),
                            ],
                        )
                    ],
                    failures=[],
                ),
                crawl_time='2026-04-18 10:00:00',
                crawl_date='2026-04-18',
            )

            self.assertTrue(storage.save_normalized_crawl_batch(first_batch))
            self.assertTrue(storage.save_normalized_crawl_batch(second_batch))

            backend = storage.get_backend()
            db_path = backend.runtime.get_db_path('2026-04-18')
            conn = sqlite3.connect(db_path)
            try:
                title_changes = conn.execute(
                    'SELECT old_title, new_title FROM title_changes ORDER BY id'
                ).fetchall()
                rank_history = conn.execute(
                    '''
                    SELECT ni.title, rh.rank, rh.crawl_time
                    FROM rank_history rh
                    JOIN news_items ni ON ni.id = rh.news_item_id
                    ORDER BY rh.id
                    '''
                ).fetchall()
            finally:
                conn.close()
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(title_changes, [('Alpha', 'Alpha v2')])
        self.assertEqual(
            rank_history,
            [
                ('Alpha v2', 1, '2026-04-18 09:00:00'),
                ('Beta', 2, '2026-04-18 09:00:00'),
                ('Alpha v2', 1, '2026-04-18 10:00:00'),
                ('Beta', 0, '2026-04-18 10:00:00'),
            ],
        )

    def test_latest_data_still_restores_failures_when_all_sources_fail(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            failed_batch = normalize_crawl_batch(
                crawl_batch=CrawlBatchResult(
                    sources=[],
                    failures=[
                        SourceFetchFailure(
                            source_id='s2',
                            source_name='平台2',
                            resolved_source_id='s2',
                            exception_type='TimeoutError',
                            message='down',
                            attempts=3,
                            retryable=True,
                        )
                    ],
                ),
                crawl_time='2026-04-18 11:00:00',
                crawl_date='2026-04-18',
            )
            self.assertTrue(storage.save_normalized_crawl_batch(failed_batch))
            latest = storage.get_latest_crawl_data()
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.items, {})
        self.assertEqual(latest.failed_ids, ['s2'])
        self.assertEqual(latest.failures[0].reason, 'TimeoutError: down')

    def test_storage_migrates_history_db_without_context_columns(self):
        tmp = self._create_workspace_tmpdir()
        output_dir = tmp / 'output'
        news_dir = output_dir / 'news'
        news_dir.mkdir(parents=True, exist_ok=True)
        db_path = news_dir / '2026-04-18.db'
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE platforms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE news_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    platform_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    url TEXT DEFAULT '',
                    mobile_url TEXT DEFAULT '',
                    first_crawl_time TEXT NOT NULL,
                    last_crawl_time TEXT NOT NULL,
                    crawl_count INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE rank_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_item_id INTEGER NOT NULL,
                    rank INTEGER NOT NULL,
                    crawl_time TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE crawl_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crawl_time TEXT NOT NULL UNIQUE,
                    total_items INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE crawl_source_status (
                    crawl_record_id INTEGER NOT NULL,
                    platform_id TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE crawl_source_failures (
                    crawl_record_id INTEGER NOT NULL,
                    platform_id TEXT NOT NULL,
                    resolved_source_id TEXT NOT NULL,
                    exception_type TEXT DEFAULT '',
                    message TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 1,
                    retryable INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE title_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_item_id INTEGER NOT NULL,
                    old_title TEXT NOT NULL,
                    new_title TEXT NOT NULL,
                    changed_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE period_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_date TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    executed_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO platforms(id, name) VALUES ('s1', '平台1');
                INSERT INTO news_items(
                    title, platform_id, rank, url, mobile_url, first_crawl_time, last_crawl_time, crawl_count
                ) VALUES (
                    'Legacy Alpha', 's1', 1, 'https://example.com/a', '', '2026-04-18 09:00:00', '2026-04-18 09:00:00', 1
                );
                INSERT INTO rank_history(news_item_id, rank, crawl_time) VALUES (1, 1, '2026-04-18 09:00:00');
                INSERT INTO crawl_records(crawl_time, total_items) VALUES ('2026-04-18 09:00:00', 1);
                """
            )
            conn.commit()
        finally:
            conn.close()

        storage = StorageManager(
            backend_type='local',
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=False,
        )
        try:
            latest = storage.get_latest_crawl_data('2026-04-18')
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.items['s1'][0].summary, '')
        self.assertEqual(latest.items['s1'][0].metadata, {})

    def test_ai_filter_analyzed_news_cache_respects_prompt_scope(self):
        tmp = self._create_workspace_tmpdir()
        storage = self._create_storage(tmp)
        try:
            repo = storage.ai_filter_repo
            repo.save_analyzed_news(
                news_ids=[1, 2],
                source_type='hotlist',
                interests_file='scope.txt',
                prompt_hash='hash-a',
                matched_ids={1},
                tag_version=1,
                model_key='openai/filter-v1',
            )
            repo.save_analyzed_news(
                news_ids=[1, 3],
                source_type='hotlist',
                interests_file='scope.txt',
                prompt_hash='hash-b',
                matched_ids={3},
                tag_version=2,
                model_key='openai/filter-v1',
            )

            all_ids = repo.get_analyzed_news_ids(interests_file='scope.txt')
            scoped_ids = repo.get_analyzed_news_ids(
                interests_file='scope.txt',
                prompt_hash='hash-a',
                tag_version=1,
                model_key='openai/filter-v1',
            )
            scoped_cache = repo.get_cached_classifications(
                [1, 2, 3],
                interests_file='scope.txt',
                prompt_hash='hash-b',
                tag_version=2,
                model_key='openai/filter-v1',
            )
            single_cache = repo.get_cached_classification(
                1,
                interests_file='scope.txt',
                prompt_hash='hash-a',
                tag_version=1,
                model_key='openai/filter-v1',
            )
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(all_ids, {1, 2, 3})
        self.assertEqual(scoped_ids, {1, 2})
        self.assertIsNotNone(single_cache)
        assert single_cache is not None
        self.assertTrue(single_cache['matched'])
        self.assertEqual(set(scoped_cache), {1, 3})
        self.assertFalse(scoped_cache[1]['matched'])
        self.assertTrue(scoped_cache[3]['matched'])

    def test_storage_migrates_ai_filter_analyzed_news_cache_scope_schema(self):
        tmp = self._create_workspace_tmpdir()
        output_dir = tmp / 'output'
        news_dir = output_dir / 'news'
        news_dir.mkdir(parents=True, exist_ok=True)
        db_path = news_dir / '2026-04-18.db'
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE ai_filter_analyzed_news (
                    news_item_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'hotlist',
                    interests_file TEXT NOT NULL DEFAULT 'ai_interests.txt',
                    prompt_hash TEXT NOT NULL,
                    matched INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (news_item_id, source_type, interests_file)
                );
                INSERT INTO ai_filter_analyzed_news (
                    news_item_id,
                    source_type,
                    interests_file,
                    prompt_hash,
                    matched,
                    created_at
                ) VALUES (7, 'hotlist', 'legacy.txt', 'legacy-hash', 1, '2026-04-18 09:00:00');
                """
            )
            conn.commit()
        finally:
            conn.close()

        storage = StorageManager(
            backend_type='local',
            data_dir=str(output_dir),
            enable_txt=False,
            enable_html=False,
        )
        try:
            backend = storage.get_backend()
            migrated_conn = backend.runtime.get_connection('2026-04-18')
            repo = storage.ai_filter_repo
            pk_columns = [
                row[1]
                for row in migrated_conn.execute("PRAGMA table_info(ai_filter_analyzed_news)").fetchall()
                if row[5] > 0
            ]
            cached = repo.get_cached_classification(
                7,
                date='2026-04-18',
                interests_file='legacy.txt',
                prompt_hash='legacy-hash',
                tag_version=0,
                model_key='',
            )
        finally:
            storage.cleanup()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(
            pk_columns,
            ['news_item_id', 'source_type', 'interests_file', 'prompt_hash', 'tag_version', 'model_key'],
        )
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertTrue(cached['matched'])
        self.assertEqual(cached['prompt_hash'], 'legacy-hash')

    def test_sqlite_runtime_enables_wal_and_new_indexes(self):
        tmp = self._create_workspace_tmpdir()
        runtime = SQLiteRuntime(data_dir=str(tmp / 'output'))
        conn = runtime.get_connection('2026-04-18')
        try:
            journal_mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list('news_items')").fetchall()
            }
            rank_indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list('rank_history')").fetchall()
            }
        finally:
            runtime.close_all()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(str(journal_mode).lower(), 'wal')
        self.assertIn('idx_news_platform_crawl_time', indexes)
        self.assertIn('idx_rank_history_news_crawl_time', rank_indexes)


if __name__ == '__main__':
    unittest.main()
