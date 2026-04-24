import json
import unittest
from pathlib import Path

from newspulse.workflow.insight.item_analyzer import InsightItemAnalyzer
from newspulse.workflow.insight.models import InsightNewsContext, InsightRankSignals, InsightSelectionEvidence, InsightSourceContext, ReducedContentBundle
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate


class QueueClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages[-1]['content'])
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class InsightItemAnalyzerTest(unittest.TestCase):
    def _context(self, news_item_id='1', title='OpenAI 发布新工具'):
        return InsightNewsContext(
            news_item_id=news_item_id,
            title=title,
            source_id='hackernews',
            source_name='Hacker News',
            rank_signals=InsightRankSignals(current_rank=1, best_rank=1, worst_rank=2, appearance_count=2, rank_trend='up'),
            source_context=InsightSourceContext(
                source_kind='article',
                summary='文章讨论新的终端工作流。',
                attributes=('host: example.com',),
            ),
            selection_evidence=InsightSelectionEvidence(
                matched_topics=('开发工具',),
                quality_score=0.95,
                semantic_score=0.8,
                llm_reasons=('工程信号强',),
            ),
        )

    def _bundle(self, news_item_id='1'):
        return ReducedContentBundle(
            news_item_id=news_item_id,
            status='ok',
            anchor_text='OpenAI 终端工作流',
            reduced_text='OpenAI 发布了新的终端工作流，并展示了代码生成、补丁应用和测试验证的一体化流程。',
            evidence_sentences=('代码生成、补丁应用和测试验证被串成闭环。',),
        )

    def test_parses_structured_json_output(self):
        client = QueueClient([
            json.dumps(
                {
                    'what_happened': 'OpenAI 发布了新的终端工作流。',
                    'key_facts': ['把生成、补丁和验证串成闭环', '强调只保留任务相关上下文'],
                    'why_it_matters': '这说明终端代理正从演示走向工程化落地。',
                    'watchpoints': ['是否开放更多工作流 API'],
                    'uncertainties': ['尚不清楚大规模团队协作表现'],
                    'evidence': ['代码生成、补丁应用和测试验证被串成闭环。'],
                    'confidence': 0.86,
                }
            )
        ])
        analyzer = InsightItemAnalyzer(
            client=client,
            analysis_config={'ITEM_PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('item.txt'), user_prompt='TITLE={title}\nCONTENT={reduced_content}'),
        )

        analysis = analyzer.analyze_one(self._context(), self._bundle())

        self.assertEqual(analysis.diagnostics['status'], 'ok')
        self.assertIn('工程化落地', analysis.why_it_matters)
        self.assertEqual(analysis.confidence, 0.86)
        self.assertEqual(len(client.calls), 1)
        self.assertIn('CONTENT=', client.calls[0])

    def test_isolates_single_item_failure(self):
        client = QueueClient([
            json.dumps({'what_happened': 'ok', 'key_facts': ['a'], 'why_it_matters': 'b', 'watchpoints': [], 'uncertainties': [], 'evidence': ['e'], 'confidence': 0.7}),
            RuntimeError('boom'),
        ])
        analyzer = InsightItemAnalyzer(
            client=client,
            analysis_config={'ITEM_PROMPT_FILE': 'ignored.txt'},
            prompt_template=PromptTemplate(path=Path('item.txt'), user_prompt='TITLE={title}\nCONTENT={reduced_content}'),
        )

        results = analyzer.analyze_many(
            [self._context('1', 'A'), self._context('2', 'B')],
            [self._bundle('1'), self._bundle('2')],
        )

        self.assertEqual(results[0].diagnostics['status'], 'ok')
        self.assertEqual(results[1].diagnostics['status'], 'error')
        self.assertIn('boom', results[1].diagnostics['error'])


if __name__ == '__main__':
    unittest.main()
