import json
import textwrap
import unittest
from pathlib import Path
from uuid import uuid4

from newspulse.storage.base import NewsData, NewsItem
from newspulse.storage.local import LocalStorageBackend
from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.models import SelectionTopic
from newspulse.workflow.selection.semantic import SemanticSelectionLayer
from newspulse.workflow.shared.contracts import HotlistItem
from newspulse.workflow.shared.options import SelectionAIOptions, SelectionOptions, SelectionSemanticOptions, SnapshotOptions
from newspulse.workflow.snapshot.service import SnapshotService

TEST_TMPDIR = Path('tmp_test_work')
TEST_TMPDIR.mkdir(exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip(), encoding='utf-8')


def _make_tmp_dir() -> Path:
    path = TEST_TMPDIR / f'case-{uuid4().hex}'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_test_ai_config(config_root: Path) -> None:
    _write_text(
        config_root / 'ai_filter' / 'prompt.txt',
        '''
        [user]
        FOCUS:
        {focus_topics}
        NEWS:
        {news_list}
        ''',
    )


def _build_storage(tmp: str) -> LocalStorageBackend:
    return LocalStorageBackend(
        data_dir=str(Path(tmp) / 'output'),
        enable_txt=False,
        enable_html=False,
        timezone='Asia/Shanghai',
    )


def _seed_hotlist(storage: LocalStorageBackend) -> None:
    crawl_time = '2026-04-19 10:00:00'
    storage.save_news_data(
        NewsData(
            date='2026-04-19',
            crawl_time=crawl_time,
            items={
                'hackernews': [
                    NewsItem(
                        title='OpenAI launches coding agent',
                        source_id='hackernews',
                        source_name='Hacker News',
                        rank=1,
                        url='https://example.com/openai',
                        mobile_url='https://m.example.com/openai',
                        crawl_time=crawl_time,
                        ranks=[1],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                    NewsItem(
                        title='GitHub ships a new open source CLI',
                        source_id='hackernews',
                        source_name='Hacker News',
                        rank=2,
                        url='https://example.com/github',
                        mobile_url='https://m.example.com/github',
                        crawl_time=crawl_time,
                        ranks=[2],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                    NewsItem(
                        title='Sports finals preview',
                        source_id='hackernews',
                        source_name='Hacker News',
                        rank=3,
                        url='https://example.com/sports',
                        mobile_url='https://m.example.com/sports',
                        crawl_time=crawl_time,
                        ranks=[3],
                        first_time=crawl_time,
                        last_time=crawl_time,
                        count=1,
                    ),
                ]
            },
            id_to_name={'hackernews': 'Hacker News'},
            failed_ids=[],
        )
    )


def _build_snapshot(storage: LocalStorageBackend):
    service = SnapshotService(
        storage,
        platform_ids=['hackernews'],
        platform_names={'hackernews': 'Hacker News'},
    )
    return service.build(SnapshotOptions(mode='current'))


class FakeEmbeddingClient:
    class _Config:
        model = 'openai/embedding-test'

    config = _Config()

    def is_enabled(self):
        return True

    def embed_texts(self, texts, **kwargs):
        vectors = []
        for text in texts:
            lowered = str(text).lower()
            if 'ai agents' in lowered or 'coding agent' in lowered or 'openai' in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif 'open source' in lowered or 'github' in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class QualityGateAIClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        user_content = messages[-1]['content']
        results = []
        for line in user_content.splitlines():
            if not line[:1].isdigit() or '. [' not in line:
                continue
            prompt_id = int(line.split('.', 1)[0])
            if 'OpenAI launches' in line:
                results.append(
                    {
                        'id': prompt_id,
                        'keep': True,
                        'score': 0.92,
                        'reasons': ['信息增量高', '值得进入分析'],
                        'evidence': '模型与代理工具相关',
                        'matched_topics': ['AI Agents'],
                    }
                )
            elif 'GitHub ships' in line:
                results.append(
                    {
                        'id': prompt_id,
                        'keep': True,
                        'score': 0.84,
                        'reasons': ['开源工具发布'],
                        'evidence': '开发者工具更新',
                        'matched_topics': ['Open Source'],
                    }
                )
        return json.dumps(results)


class SemanticSelectionLayerTest(unittest.TestCase):
    def test_semantic_layer_filters_unrelated_items(self):
        layer = SemanticSelectionLayer(embedding_client=FakeEmbeddingClient())
        topics = [
            SelectionTopic(topic_id=1, label='AI Agents', description='AI coding agents', priority=1),
            SelectionTopic(topic_id=2, label='Open Source', description='Open source developer tools', priority=2),
        ]
        items = [
            HotlistItem(news_item_id='1', source_id='hn', source_name='Hacker News', title='OpenAI launches coding agent'),
            HotlistItem(news_item_id='2', source_id='hn', source_name='Hacker News', title='GitHub ships a new open source CLI'),
            HotlistItem(news_item_id='3', source_id='hn', source_name='Hacker News', title='Sports finals preview'),
        ]

        result = layer.select(
            items,
            topics,
            SelectionSemanticOptions(top_k=2, min_score=0.55, direct_threshold=0.95),
        )

        self.assertFalse(result.diagnostics['skipped'])
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual([item.news_item_id for item in result.passed_items], ['1', '2'])
        self.assertEqual([item.news_item_id for item in result.rejected_items], ['3'])
        self.assertEqual(result.diagnostics['model'], 'openai/embedding-test')

    def test_semantic_layer_uses_summary_and_metadata_context(self):
        layer = SemanticSelectionLayer(embedding_client=FakeEmbeddingClient())
        topics = [SelectionTopic(topic_id=1, label='AI Agents', description='AI agent tooling', priority=1)]
        github_item = HotlistItem(
            news_item_id='gh-1',
            source_id='github-trending-today',
            source_name='GitHub Trending',
            title='openai/openai-agents-python',
            summary='Official OpenAI Agents SDK for Python',
            metadata={
                'source_kind': 'github_repository',
                'github': {
                    'language': 'Python',
                    'topics': ['openai', 'agent', 'sdk'],
                    'stars_today': 842,
                },
            },
        )

        result = layer.select(
            [github_item],
            topics,
            SelectionSemanticOptions(top_k=1, min_score=0.55, direct_threshold=0.95),
        )

        self.assertEqual([item.news_item_id for item in result.passed_items], ['gh-1'])
        self.assertIn('Official OpenAI Agents SDK for Python', result.candidates[0].evidence['item_text'])
        self.assertIn('language: Python', result.candidates[0].evidence['context_attributes'])


class SemanticAISelectionIntegrationTest(unittest.TestCase):
    def test_ai_selection_uses_semantic_gate_before_llm(self):
        tmp_root = _make_tmp_dir()
        config_root = tmp_root / 'config'
        _write_test_ai_config(config_root)
        _write_text(
            config_root / 'custom' / 'ai' / 'unit.txt',
            '''
            [TOPIC_CATALOG]

            [AI Agents]
            AI coding agents and agent tooling
            + AI agent
            + OpenAI Agents
            @priority: 1

            [Open Source]
            Open source developer tools and repos
            + open source
            + GitHub
            @priority: 2
            ''',
        )

        storage = _build_storage(str(tmp_root))
        try:
            _seed_hotlist(storage)
            snapshot = _build_snapshot(storage)
            client = QualityGateAIClient()

            strategy = AISelectionStrategy(
                storage_manager=storage,
                client=client,
                embedding_client=FakeEmbeddingClient(),
                filter_config={'PROMPT_FILE': 'prompt.txt'},
                config_root=config_root,
                sleep_func=lambda _: None,
            )

            result = strategy.run(
                snapshot,
                SelectionOptions(
                    strategy='ai',
                    ai=SelectionAIOptions(
                        interests_file='unit.txt',
                        batch_size=10,
                        batch_interval=0,
                        min_score=0.7,
                    ),
                    semantic=SelectionSemanticOptions(
                        enabled=True,
                        top_k=2,
                        min_score=0.55,
                        direct_threshold=0.95,
                    ),
                ),
            )

            self.assertEqual(result.strategy, 'ai')
            self.assertEqual(
                [item.title for item in result.qualified_items],
                ['OpenAI launches coding agent', 'GitHub ships a new open source CLI'],
            )
            self.assertEqual(len(result.rejected_items), 1)
            self.assertEqual(result.rejected_items[0].rejected_stage, 'semantic')
            self.assertEqual(client.calls, 1)
            self.assertEqual(result.diagnostics['semantic_passed_count'], 2)
            self.assertEqual(result.diagnostics['semantic_rejected_count'], 1)
            self.assertEqual(result.diagnostics['semantic_model'], 'openai/embedding-test')
            self.assertEqual(len(result.diagnostics['semantic_topics']), 2)
            self.assertEqual(len(result.diagnostics['semantic_candidates']), 2)
        finally:
            storage.cleanup()


if __name__ == '__main__':
    unittest.main()
