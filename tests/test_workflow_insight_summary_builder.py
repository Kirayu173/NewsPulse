import unittest

from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
from newspulse.workflow.insight.summary_builder import InsightSummaryBuilder


class InsightSummaryBuilderTest(unittest.TestCase):
    def test_build_many_creates_item_theme_and_report_summaries(self):
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
            ),
            InsightNewsContext(
                news_item_id="2",
                title="GitHub ships MCP toolkit",
                source_id="github-trending-today",
                source_name="GitHub Trending",
                rank_signals=InsightRankSignals(current_rank=2, rank_trend="stable"),
                source_context=InsightSourceContext(source_kind="github_repository"),
                selection_evidence=InsightSelectionEvidence(
                    matched_topics=("AI Agents", "Open Source"),
                    semantic_score=0.79,
                    quality_score=0.9,
                    llm_reasons=("developer workflow signal",),
                ),
            ),
        ]

        bundle = InsightSummaryBuilder().build_many(contexts)

        self.assertEqual(len(bundle.item_summaries), 2)
        self.assertEqual(len(bundle.theme_summaries), 1)
        self.assertIsNotNone(bundle.report_summary)
        self.assertEqual(bundle.item_summaries[0].kind, "item")
        self.assertEqual(bundle.item_summaries[0].summary, "Terminal-native coding workflow with patch and verify loops.")
        self.assertEqual(bundle.item_summaries[0].metadata["attributes"], ["host: example.com", "developer tools"])
        self.assertEqual(bundle.item_summaries[0].evidence_topics, ["AI Agents", "Coding Workflow"])
        self.assertEqual(bundle.item_summaries[0].evidence_notes, ["clear workflow angle", "strong launch signal"])
        self.assertTrue(bundle.item_summaries[0].expanded)

        theme = bundle.theme_summaries[0]
        self.assertEqual(theme.kind, "theme")
        self.assertEqual(theme.title, "AI Agents")
        self.assertEqual(theme.item_ids, ["1", "2"])
        self.assertEqual(theme.metadata["representative_item_ids"], ["1", "2"])
        self.assertEqual(theme.sources, ["Hacker News", "GitHub Trending"])
        self.assertIn("AI Agents", theme.evidence_topics)
        self.assertTrue(theme.expanded)

        self.assertEqual(bundle.report_summary.kind, "report")
        self.assertEqual(bundle.report_summary.theme_keys, ["theme:ai-agents"])
        self.assertEqual(len(bundle.summaries), 4)

    def test_source_does_not_drive_theme_grouping(self):
        contexts = [
            InsightNewsContext(
                news_item_id="1",
                title="OpenAI coding agent",
                source_id="hackernews",
                source_name="Hacker News",
                selection_evidence=InsightSelectionEvidence(
                    matched_topics=("AI Agents",),
                    llm_reasons=("agent workflow",),
                ),
            ),
            InsightNewsContext(
                news_item_id="2",
                title="Another AI coding agent",
                source_id="producthunt",
                source_name="Product Hunt",
                selection_evidence=InsightSelectionEvidence(
                    matched_topics=("AI Agents",),
                    llm_reasons=("launch signal",),
                ),
            ),
        ]

        bundle = InsightSummaryBuilder().build_many(contexts)

        self.assertEqual(len(bundle.theme_summaries), 1)
        self.assertEqual(set(bundle.theme_summaries[0].item_ids), {"1", "2"})
        self.assertEqual(set(bundle.theme_summaries[0].metadata["source_evidence"]), {"Hacker News", "Product Hunt"})

    def test_theme_sorting_prioritizes_llm_reasons_without_time_weighting(self):
        contexts = [
            InsightNewsContext(
                news_item_id="1",
                title="Low reason but many items",
                source_id="a",
                source_name="A",
                selection_evidence=InsightSelectionEvidence(matched_topics=("Source Scale",)),
            ),
            InsightNewsContext(
                news_item_id="2",
                title="High reason item",
                source_id="b",
                source_name="B",
                selection_evidence=InsightSelectionEvidence(
                    matched_topics=("Reason Rich",),
                    llm_reasons=("reason one", "reason two"),
                ),
            ),
        ]

        bundle = InsightSummaryBuilder().build_many(contexts)

        self.assertEqual([summary.title for summary in bundle.theme_summaries], ["Reason Rich", "Source Scale"])


if __name__ == "__main__":
    unittest.main()
