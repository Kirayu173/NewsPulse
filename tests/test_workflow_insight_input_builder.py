import unittest

from newspulse.workflow.insight.input_builder import InsightInputBuilder
from newspulse.workflow.shared.contracts import HotlistItem, SelectionGroup, SelectionResult


class InsightInputBuilderTest(unittest.TestCase):
    def test_builds_useful_only_contexts_for_generic_github_and_hn_items(self):
        generic = HotlistItem(
            news_item_id='1',
            source_id='thepaper',
            source_name='澎湃新闻',
            title='大模型应用进入交付阶段',
            summary='多家厂商开始交付企业级智能体项目。',
            url='https://example.com/article?utm_source=x',
            current_rank=2,
            ranks=[4, 2],
            count=2,
            rank_timeline=[{'time': '09:00', 'rank': 4}, {'time': '10:00', 'rank': 2}],
        )
        github = HotlistItem(
            news_item_id='2',
            source_id='github-trending-today',
            source_name='GitHub Trending',
            title='openai/codex',
            summary='A coding agent for software tasks.',
            url='https://github.com/openai/codex',
            metadata={
                'source_kind': 'github_repository',
                'github': {
                    'full_name': 'openai/codex',
                    'description': 'A coding agent for software tasks.',
                    'language': 'Python',
                    'topics': ['agent', 'llm', 'automation'],
                    'stars_total': 12000,
                    'forks_total': 800,
                    'stars_today': 900,
                },
            },
            current_rank=1,
            ranks=[1],
            count=1,
        )
        hn = HotlistItem(
            news_item_id='3',
            source_id='hackernews',
            source_name='Hacker News',
            title='A new terminal-native coding workflow',
            summary='HN users are discussing a new terminal workflow.',
            url='https://news.ycombinator.com/item?id=1',
            current_rank=3,
            ranks=[3],
            count=1,
        )
        selection = SelectionResult(
            strategy='ai',
            selected_items=[generic, github, hn],
            total_candidates=3,
            total_selected=3,
            diagnostics={
                'selected_matches': [
                    {'news_item_id': '1', 'quality_score': 0.88, 'decision_layer': 'llm_quality_gate', 'matched_topics': ['AI 交付'], 'reasons': ['企业落地信号增强']},
                    {'news_item_id': '2', 'quality_score': 0.95, 'decision_layer': 'llm_quality_gate', 'matched_topics': ['开发工具'], 'reasons': ['开源工具热度高']},
                ],
                'semantic_candidates': [
                    {'news_item_id': '1', 'score': 0.72},
                    {'news_item_id': '2', 'score': 0.81},
                ],
                'llm_decisions': [
                    {'news_item_id': '1', 'quality_score': 0.88, 'matched_topics': ['AI 交付'], 'reasons': ['企业落地信号增强']},
                    {'news_item_id': '2', 'quality_score': 0.95, 'matched_topics': ['开发工具'], 'reasons': ['开源工具热度高']},
                ],
            },
        )

        contexts = InsightInputBuilder().build(None, selection)

        self.assertEqual(len(contexts), 3)
        self.assertEqual(contexts[0].rank_signals.rank_trend, 'up')
        self.assertEqual(contexts[0].selection_evidence.matched_topics, ('AI 交付',))
        self.assertNotIn('rank_timeline', contexts[0].source_context.metadata)
        self.assertEqual(contexts[1].source_context.source_kind, 'github_repository')
        self.assertEqual(contexts[1].source_context.metadata['full_name'], 'openai/codex')
        self.assertIn('host: example.com', contexts[0].source_context.attributes)
        self.assertEqual(contexts[2].source_context.source_kind, 'hackernews_item')
        self.assertIn('host: news.ycombinator.com', contexts[2].source_context.attributes)

    def test_keyword_group_labels_feed_theme_topics_when_ai_topics_are_missing(self):
        item = HotlistItem(
            news_item_id='1',
            source_id='thepaper',
            source_name='澎湃新闻',
            title='科技政策更新',
            current_rank=1,
        )
        selection = SelectionResult(
            strategy='keyword',
            groups=[SelectionGroup(key='technology', label='科技政策', items=[item])],
            selected_items=[item],
            total_candidates=1,
            total_selected=1,
            diagnostics={},
        )

        contexts = InsightInputBuilder().build(None, selection)

        self.assertEqual(contexts[0].selection_evidence.matched_topics, ('科技政策',))


if __name__ == '__main__':
    unittest.main()
