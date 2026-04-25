import unittest

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
from newspulse.workflow.insight.summary_builder import InsightSummaryBuilder
from newspulse.workflow.shared.contracts import HotlistSnapshot, InsightResult, InsightSection, SelectionResult
from newspulse.workflow.shared.options import InsightOptions


class StubInputBuilder:
    def build(self, snapshot, selection, *, max_items=0):
        items = [
            InsightNewsContext(
                news_item_id="1",
                title="OpenAI 发布终端工作流",
                source_id="hackernews",
                source_name="Hacker News",
                rank_signals=InsightRankSignals(current_rank=1),
                source_context=InsightSourceContext(source_kind="article", summary="summary one"),
                selection_evidence=InsightSelectionEvidence(matched_topics=("开发工具",), quality_score=0.9),
            ),
            InsightNewsContext(
                news_item_id="2",
                title="GitHub 新项目走热",
                source_id="github-trending-today",
                source_name="GitHub Trending",
                rank_signals=InsightRankSignals(current_rank=2),
                source_context=InsightSourceContext(source_kind="github_repository", summary="summary two"),
                selection_evidence=InsightSelectionEvidence(matched_topics=("开源趋势",), quality_score=0.95),
            ),
        ]
        return items[:max_items] if max_items > 0 else items


class StubAggregate:
    def generate(self, summary_bundle, contexts):
        item_ids = [
            item_id
            for summary in summary_bundle.item_summaries
            for item_id in summary.item_ids
        ]
        return (
            [
                InsightSection(
                    key="core_trends",
                    title="Core Trends",
                    content="终端代理与开源项目同时升温。",
                    metadata={"supporting_news_ids": item_ids},
                )
            ],
            '{"sections": []}',
            {
                "summary_count": len(summary_bundle.summaries),
                "item_summary_count": len(summary_bundle.item_summaries),
                "theme_summary_count": len(summary_bundle.theme_summaries),
                "section_count": 1,
            },
        )


class WorkflowInsightServiceTest(unittest.TestCase):
    def test_noop_strategy_returns_empty_insight_result(self):
        snapshot = HotlistSnapshot(mode="current", generated_at="2026-04-20 10:00:00")
        selection = SelectionResult(strategy="keyword")
        service = InsightService()

        result = service.run(snapshot, selection, InsightOptions(enabled=False, strategy="ai"))

        self.assertIsInstance(result, InsightResult)
        self.assertFalse(result.enabled)
        self.assertEqual(result.strategy, "noop")
        self.assertEqual(result.sections, [])
        self.assertEqual(result.summaries, [])
        self.assertTrue(result.diagnostics["skipped"])

    def test_ai_strategy_runs_summary_pipeline_and_emits_summary_payloads(self):
        snapshot = HotlistSnapshot(mode="current", generated_at="2026-04-20 10:00:00")
        selection = SelectionResult(strategy="ai", total_selected=2)
        strategy = AIInsightStrategy(
            client=object(),
            input_builder=StubInputBuilder(),
            summary_builder=InsightSummaryBuilder(),
            aggregate_generator=StubAggregate(),
            analysis_config={},
        )
        service = InsightService(ai_strategy=strategy)

        result = service.run(snapshot, selection, InsightOptions(enabled=True, strategy="ai", mode="current", max_items=2))

        self.assertTrue(result.enabled)
        self.assertEqual(result.strategy, "ai")
        self.assertEqual(len([summary for summary in result.summaries if summary.kind == "item"]), 2)
        self.assertEqual(result.sections[0].metadata["supporting_news_ids"], ["1", "2"])
        self.assertEqual(result.diagnostics["item_summary_count"], 2)
        self.assertFalse(result.diagnostics["llm_cache_enabled"])
        self.assertEqual(result.diagnostics["llm_cache_hits"], 0)
        self.assertEqual(result.diagnostics["llm_cache_misses"], 0)
        self.assertEqual(len(result.diagnostics["input_contexts"]), 2)
        self.assertEqual(len(result.diagnostics["item_summary_payloads"]), 2)
        self.assertEqual(len(result.diagnostics["theme_summary_payloads"]), 2)
        self.assertNotIn("item_" + "analysis_payloads", result.diagnostics)
        self.assertNotIn("content_payloads", result.diagnostics)
        self.assertNotIn("reduced_bundles", result.diagnostics)
        self.assertNotIn("brief" + "_payloads", result.diagnostics)

    def test_service_raises_for_unknown_strategy(self):
        snapshot = HotlistSnapshot(mode="current", generated_at="2026-04-20 10:00:00")
        selection = SelectionResult(strategy="keyword")
        service = InsightService()

        with self.assertRaises(NotImplementedError):
            service.run(snapshot, selection, InsightOptions(enabled=True, strategy="custom"))


if __name__ == "__main__":
    unittest.main()
