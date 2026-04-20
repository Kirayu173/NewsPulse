import shutil
import sqlite3
import unittest
import uuid
from pathlib import Path

from newspulse.crawler import CrawlBatchResult, SourceFetchFailure, SourceFetchResult
from newspulse.crawler.sources.base import SourceItem
from newspulse.storage import StorageManager, normalize_crawl_batch


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


if __name__ == '__main__':
    unittest.main()
