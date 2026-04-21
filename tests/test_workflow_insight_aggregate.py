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
                            'title': 'Core Trends',
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
        self.assertEqual(sections[0].metadata['supporting_news_ids'], ['1', '2'])
        self.assertEqual(diagnostics['section_count'], 1)
        self.assertTrue(raw_response)
        self.assertIn('COUNT=2', client.calls[0])

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

        self.assertEqual(sections[0].metadata['section_generator'], 'aggregate_fallback')
        self.assertIn('error', diagnostics)


if __name__ == '__main__':
    unittest.main()
