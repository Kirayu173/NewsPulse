import unittest

from newspulse.workflow.insight.content_reducer import InsightContentReducer
from newspulse.workflow.insight.models import InsightContentPayload, InsightNewsContext, InsightRankSignals, InsightSelectionEvidence, InsightSourceContext


class EmptyPrimary:
    name = 'primary'

    def rank(self, sentences, anchor_text):
        return [], {'backend': 'primary_empty'}


class InsightContentReducerTest(unittest.TestCase):
    def _context(self):
        return InsightNewsContext(
            news_item_id='1',
            title='OpenAI 发布新的终端工作流',
            source_id='hackernews',
            source_name='Hacker News',
            rank_signals=InsightRankSignals(current_rank=1, best_rank=1, worst_rank=3, appearance_count=3, rank_trend='up'),
            source_context=InsightSourceContext(
                source_kind='article',
                summary='文章讨论终端工作流如何缩短开发闭环。',
                attributes=('host: example.com', 'route: article_content'),
            ),
            selection_evidence=InsightSelectionEvidence(
                matched_topics=('开发工具',),
                quality_score=0.93,
                llm_reasons=('具备真实工程信号',),
            ),
        )

    def test_reducer_filters_noise_and_respects_budget(self):
        reducer = InsightContentReducer(reduced_chars=180)
        payload = InsightContentPayload(
            news_item_id='1',
            status='ok',
            source_type='article',
            content_text='''
            点击下载 APP 获取更多精彩内容。
            OpenAI 发布了一套终端工作流，允许开发者把代码生成、补丁应用和测试验证串成一个闭环。
            该工作流强调只保留与任务相关的上下文，并把验证结果回写到后续步骤中。
            责任编辑：测试。
            团队还展示了如何把失败的命令、补丁和日志收口成可审阅的证据片段。
            更多精彩请关注我们。
            ''',
        )

        bundle = reducer.reduce_one(self._context(), payload)

        self.assertEqual(bundle.status, 'ok')
        self.assertLessEqual(len(bundle.reduced_text), 183)
        self.assertNotIn('点击下载', bundle.reduced_text)
        self.assertIn('终端工作流', bundle.reduced_text)
        self.assertTrue(bundle.evidence_sentences)

    def test_reducer_falls_back_when_primary_returns_nothing(self):
        reducer = InsightContentReducer(reduced_chars=200, primary=EmptyPrimary())
        payload = InsightContentPayload(
            news_item_id='1',
            status='ok',
            source_type='article',
            content_text='第一句说明发生了什么。第二句说明为什么重要。第三句列出后续观察点。',
        )

        bundle = reducer.reduce_one(self._context(), payload)

        self.assertTrue(bundle.selected_sentences)
        self.assertTrue(bundle.diagnostics['fallback_used'])


if __name__ == '__main__':
    unittest.main()
