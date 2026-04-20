import unittest

from newspulse.workflow.selection.context_builder import build_selection_context
from newspulse.workflow.shared.contracts import HotlistItem


class SelectionContextBuilderTest(unittest.TestCase):
    def test_build_selection_context_for_generic_item(self):
        item = HotlistItem(
            news_item_id='1',
            source_id='hackernews',
            source_name='Hacker News',
            title='OpenAI launches coding agent',
            summary='Agent runtime now supports tool calling and tracing.',
            current_rank=1,
        )

        context = build_selection_context(item)

        self.assertEqual(context.summary, 'Agent runtime now supports tool calling and tracing.')
        self.assertIn('OpenAI launches coding agent', context.embedding_text)
        self.assertIn('summary: Agent runtime now supports tool calling and tracing.', context.llm_text)
        self.assertEqual(context.attributes, ())

    def test_build_selection_context_for_github_item(self):
        item = HotlistItem(
            news_item_id='2',
            source_id='github-trending-today',
            source_name='GitHub Trending',
            title='openai/openai-agents-python',
            summary='',
            current_rank=2,
            metadata={
                'source_context_version': 1,
                'source_kind': 'github_repository',
                'github': {
                    'full_name': 'openai/openai-agents-python',
                    'description': 'Official OpenAI Agents SDK for Python',
                    'language': 'Python',
                    'topics': ['openai', 'agent', 'sdk'],
                    'stars_today': 842,
                    'stars_total': 12345,
                    'forks_total': 678,
                    'pushed_at': '2026-04-19T00:00:00Z',
                    'source_variant': 'trending_html',
                },
            },
        )

        context = build_selection_context(item)

        self.assertEqual(context.summary, 'Official OpenAI Agents SDK for Python')
        self.assertIn('language: Python', context.attributes)
        self.assertIn('topics: openai, agent, sdk', context.attributes)
        self.assertIn('stars_today: 842', context.attributes)
        self.assertIn('stars_total: 12,345', context.attributes)
        self.assertIn('updated: 2026-04-19', context.attributes)
        self.assertIn('summary: Official OpenAI Agents SDK for Python', context.llm_text)


if __name__ == '__main__':
    unittest.main()
