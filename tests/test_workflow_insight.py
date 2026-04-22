import unittest

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.insight.models import InsightContentPayload, InsightItemAnalysis, InsightNewsContext, InsightRankSignals, InsightSelectionEvidence, InsightSourceContext, ReducedContentBundle
from newspulse.workflow.shared.contracts import HotlistSnapshot, InsightResult, InsightSection, SelectionResult
from newspulse.workflow.shared.options import InsightOptions


class StubInputBuilder:
    def build(self, snapshot, selection, *, max_items=0):
        items = [
            InsightNewsContext(
                news_item_id='1',
                title='OpenAI 发布终端工作流',
                source_id='hackernews',
                source_name='Hacker News',
                rank_signals=InsightRankSignals(current_rank=1),
                source_context=InsightSourceContext(source_kind='article', summary='summary'),
                selection_evidence=InsightSelectionEvidence(matched_topics=('开发工具',), quality_score=0.9),
            ),
            InsightNewsContext(
                news_item_id='2',
                title='GitHub 新项目走热',
                source_id='github-trending-today',
                source_name='GitHub Trending',
                rank_signals=InsightRankSignals(current_rank=2),
                source_context=InsightSourceContext(source_kind='github_repository', summary='summary'),
                selection_evidence=InsightSelectionEvidence(matched_topics=('开源趋势',), quality_score=0.95),
            ),
        ]
        return items[:max_items] if max_items > 0 else items


class StubFetcher:
    def fetch_many(self, contexts):
        return [
            InsightContentPayload(news_item_id=context.news_item_id, status='ok', source_type=context.source_context.source_kind or 'article', content_text='正文内容' * 20, content_markdown='正文内容' * 20)
            for context in contexts
        ]


class StubReducer:
    def reduce_many(self, contexts, payloads):
        return [
            ReducedContentBundle(
                news_item_id=context.news_item_id,
                status='ok',
                anchor_text=context.title,
                reduced_text=f'{context.title} 的压缩正文',
                selected_sentences=(f'{context.title} 的压缩正文',),
                evidence_sentences=(f'{context.title} 的证据句',),
                reducer_name='stub',
            )
            for context in contexts
        ]


class StubAnalyzer:
    def analyze_many(self, contexts, bundles):
        return [
            InsightItemAnalysis(
                news_item_id=context.news_item_id,
                title=context.title,
                what_happened=f'{context.title} 发生了什么',
                why_it_matters=f'{context.title} 为什么重要',
                evidence=(f'{context.title} 的证据句',),
                diagnostics={'status': 'ok'},
            )
            for context in contexts
        ]


class StubAggregate:
    def generate(self, item_analyses, contexts):
        return (
            [
                InsightSection(
                    key='core_trends',
                    title='Core Trends',
                    content='终端代理与开源项目同时升温。',
                    metadata={'supporting_news_ids': ['1', '2']},
                )
            ],
            '{"sections": []}',
            {'item_count': len(item_analyses), 'section_count': 1},
        )


class WorkflowInsightServiceTest(unittest.TestCase):
    def test_noop_strategy_returns_empty_insight_result(self):
        snapshot = HotlistSnapshot(mode='current', generated_at='2026-04-20 10:00:00')
        selection = SelectionResult(strategy='keyword')
        service = InsightService()

        result = service.run(snapshot, selection, InsightOptions(enabled=False, strategy='ai'))

        self.assertIsInstance(result, InsightResult)
        self.assertFalse(result.enabled)
        self.assertEqual(result.strategy, 'noop')
        self.assertEqual(result.sections, [])
        self.assertTrue(result.diagnostics['skipped'])

    def test_ai_strategy_runs_native_pipeline_and_emits_debug_payloads(self):
        snapshot = HotlistSnapshot(mode='current', generated_at='2026-04-20 10:00:00')
        selection = SelectionResult(strategy='ai', total_selected=2)
        strategy = AIInsightStrategy(
            client=object(),
            input_builder=StubInputBuilder(),
            content_fetcher=StubFetcher(),
            content_reducer=StubReducer(),
            item_analyzer=StubAnalyzer(),
            aggregate_generator=StubAggregate(),
            analysis_config={},
        )
        service = InsightService(ai_strategy=strategy)

        result = service.run(snapshot, selection, InsightOptions(enabled=True, strategy='ai', mode='current', max_items=2))

        self.assertTrue(result.enabled)
        self.assertEqual(result.strategy, 'ai')
        self.assertEqual(len(result.item_analyses), 2)
        self.assertEqual(result.sections[0].metadata['supporting_news_ids'], ['1', '2'])
        self.assertEqual(result.diagnostics['content_fetch_count'], 2)
        self.assertFalse(result.diagnostics['content_async_enabled'])
        self.assertEqual(result.diagnostics['content_max_concurrency'], 1)
        self.assertEqual(result.diagnostics['content_request_timeout'], 12)
        self.assertEqual(len(result.diagnostics['input_contexts']), 2)
        self.assertEqual(len(result.diagnostics['content_payloads']), 2)
        self.assertEqual(len(result.diagnostics['reduced_bundles']), 2)

    def test_service_raises_for_unknown_strategy(self):
        snapshot = HotlistSnapshot(mode='current', generated_at='2026-04-20 10:00:00')
        selection = SelectionResult(strategy='keyword')
        service = InsightService()

        with self.assertRaises(NotImplementedError):
            service.run(snapshot, selection, InsightOptions(enabled=True, strategy='custom'))


if __name__ == '__main__':
    unittest.main()
