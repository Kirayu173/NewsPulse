import json
import unittest
from pathlib import Path

from newspulse.workflow.insight.aggregate import InsightAggregateGenerator
from newspulse.workflow.insight.models import InsightItemAnalysis, InsightNewsContext, InsightRankSignals, InsightSelectionEvidence, InsightSourceContext
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate


class StubClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages[-1]['content'])
        return self.response


class InsightAggregateGeneratorTest(unittest.TestCase):
    def _contexts(self):
        return [
            InsightNewsContext(
                news_item_id='1',
                title='OpenAI 发布终端工作流',
                source_id='hackernews',
                source_name='Hacker News',
                rank_signals=InsightRankSignals(current_rank=1),
                source_context=InsightSourceContext(source_kind='article', summary='summary'),
                selection_evidence=InsightSelectionEvidence(matched_topics=('开发工具',)),
            ),
            InsightNewsContext(
                news_item_id='2',
                title='GitHub 上新的自动化项目走热',
                source_id='github-trending-today',
                source_name='GitHub Trending',
                rank_signals=InsightRankSignals(current_rank=2),
                source_context=InsightSourceContext(source_kind='github_repository', summary='summary'),
                selection_evidence=InsightSelectionEvidence(matched_topics=('开源趋势',)),
            ),
        ]

    def test_builds_sections_with_supporting_metadata(self):
        client = StubClient(
            json.dumps(
                {
                    'sections': [
                        {
                            'key': 'core_trends',
                            'title': 'Drifted Title',
                            'content': '终端代理与开源自动化项目正在同时升温。',
                            'summary': '终端代理与开源自动化同时升温。',
                            'supporting_news_ids': ['1', '2'],
                            'supporting_topics': ['开发工具', '开源趋势'],
                            'source_distribution': {'Hacker News': 1, 'GitHub Trending': 1},
                        }
                    ]
                }
            )
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={'PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('agg.txt'), user_prompt='COUNT={news_count}\n{item_analyses_json}'),
        )
        analyses = [
            InsightItemAnalysis(news_item_id='1', title='A', what_happened='A', why_it_matters='A', diagnostics={'status': 'ok'}),
            InsightItemAnalysis(news_item_id='2', title='B', what_happened='B', why_it_matters='B', diagnostics={'status': 'ok'}),
        ]

        sections, raw_response, diagnostics = generator.generate(analyses, self._contexts())

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, '核心趋势')
        self.assertEqual(sections[0].metadata['supporting_news_ids'], ['1', '2'])
        self.assertEqual(diagnostics['section_count'], 1)
        self.assertTrue(raw_response)
        self.assertIn('COUNT=2', client.calls[0])

    def test_supports_dynamic_section_count_with_fixed_titles(self):
        client = StubClient(
            json.dumps(
                {
                    'sections': [
                        {
                            'key': 'core_trends',
                            'title': 'Whatever',
                            'content': '终端工作流与开源自动化正在汇聚到同一条工程化主线。',
                            'summary': '工程化主线收束。',
                            'supporting_news_ids': ['1', '2'],
                        },
                        {
                            'key': 'signals',
                            'title': 'Another Title',
                            'content': '产品化叙事开始让“生成-修补-验证”闭环成为默认卖点。',
                            'summary': '闭环能力成为卖点。',
                            'supporting_news_ids': ['1'],
                        },
                    ]
                }
            )
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={'PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('agg.txt'), user_prompt='{item_analyses_json}'),
        )
        analyses = [
            InsightItemAnalysis(news_item_id='1', title='A', what_happened='A', why_it_matters='A', diagnostics={'status': 'ok'}),
            InsightItemAnalysis(news_item_id='2', title='B', what_happened='B', why_it_matters='B', diagnostics={'status': 'ok'}),
        ]

        sections, _, diagnostics = generator.generate(analyses, self._contexts())

        self.assertEqual(diagnostics['section_count'], 2)
        self.assertEqual([section.key for section in sections], ['core_trends', 'signals'])
        self.assertEqual([section.title for section in sections], ['核心趋势', '关键信号'])

    def test_discards_duplicate_section_keys_from_llm_payload(self):
        client = StubClient(
            json.dumps(
                {
                    'sections': [
                        {
                            'key': 'signals',
                            'title': 'Signal One',
                            'content': '第一条信号。',
                            'summary': '第一条。',
                            'supporting_news_ids': ['1'],
                        },
                        {
                            'key': 'signals',
                            'title': 'Signal Two',
                            'content': '第二条信号。',
                            'summary': '第二条。',
                            'supporting_news_ids': ['2'],
                        },
                    ]
                }
            )
        )
        generator = InsightAggregateGenerator(
            client=client,
            analysis_config={'PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('agg.txt'), user_prompt='{item_analyses_json}'),
        )
        analyses = [
            InsightItemAnalysis(news_item_id='1', title='A', what_happened='A', why_it_matters='A', diagnostics={'status': 'ok'}),
            InsightItemAnalysis(news_item_id='2', title='B', what_happened='B', why_it_matters='B', diagnostics={'status': 'ok'}),
        ]

        sections, _, diagnostics = generator.generate(analyses, self._contexts())

        self.assertEqual(diagnostics['section_count'], 1)
        self.assertEqual([section.key for section in sections], ['signals'])
        self.assertEqual(sections[0].content, '第一条信号。')
        self.assertEqual(sections[0].title, '关键信号')

    def test_falls_back_when_payload_is_invalid(self):
        generator = InsightAggregateGenerator(
            client=StubClient('not-json'),
            analysis_config={'PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('agg.txt'), user_prompt='{item_analyses_json}'),
        )
        analyses = [
            InsightItemAnalysis(news_item_id='1', title='A', what_happened='A', why_it_matters='Important', diagnostics={'status': 'ok'}),
        ]

        sections, _, diagnostics = generator.generate(analyses, self._contexts()[:1])

        self.assertEqual(sections[0].title, '核心趋势')
        self.assertEqual(sections[0].metadata['section_generator'], 'aggregate_fallback')
        self.assertIn('error', diagnostics)


if __name__ == '__main__':
    unittest.main()
