import unittest

from newspulse.workflow.insight.brief_builder import InsightBriefBuilder
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)


class InsightBriefBuilderTest(unittest.TestCase):
    def test_build_many_converts_contexts_to_compact_briefs(self):
        contexts = [
            InsightNewsContext(
                news_item_id="1",
                title="OpenAI launches a coding agent",
                source_id="hackernews",
                source_name="Hacker News",
                url="https://example.com/1",
                rank_signals=InsightRankSignals(current_rank=1, rank_trend="up"),
                source_context=InsightSourceContext(
                    source_kind="article",
                    summary="Terminal-native coding workflow with patch and verify loops.",
                    attributes=("host: example.com", "route: article_content", "developer tools"),
                ),
                selection_evidence=InsightSelectionEvidence(
                    matched_topics=("AI Agents", "Coding Workflow", "AI Agents"),
                    semantic_score=0.83,
                    quality_score=0.94,
                    llm_reasons=("clear workflow angle", "clear workflow angle", "strong launch signal"),
                ),
            )
        ]

        briefs = InsightBriefBuilder().build_many(contexts)

        self.assertEqual(len(briefs), 1)
        brief = briefs[0]
        self.assertEqual(brief.news_item_id, "1")
        self.assertEqual(brief.summary, "Terminal-native coding workflow with patch and verify loops.")
        self.assertEqual(list(brief.attributes), ["host: example.com", "developer tools"])
        self.assertEqual(list(brief.matched_topics), ["AI Agents", "Coding Workflow"])
        self.assertEqual(list(brief.llm_reasons), ["clear workflow angle", "strong launch signal"])
        self.assertEqual(brief.current_rank, 1)
        self.assertEqual(brief.rank_trend, "up")

    def test_build_one_synthesizes_summary_when_source_summary_is_missing(self):
        context = InsightNewsContext(
            news_item_id="2",
            title="GitHub ships MCP toolkit",
            source_id="github-trending-today",
            source_name="GitHub Trending",
            rank_signals=InsightRankSignals(current_rank=2, rank_trend="stable"),
            source_context=InsightSourceContext(source_kind="github_repository"),
            selection_evidence=InsightSelectionEvidence(
                matched_topics=("Open Source", "Developer Tools"),
                llm_reasons=("high-signal repository release",),
            ),
        )

        brief = InsightBriefBuilder().build_one(context)

        self.assertIsNotNone(brief)
        self.assertIn("主题:", brief.summary)
        self.assertIn("Open Source", brief.summary)
        self.assertEqual(brief.source_kind, "github_repository")


if __name__ == "__main__":
    unittest.main()
