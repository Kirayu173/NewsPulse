import unittest

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.shared.contracts import (
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    InsightSummary,
    InsightSummaryBundle,
    SelectionResult,
)
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
                "section_count": 1,
            },
        )


class StubSummaryBuilder:
    def __init__(self):
        self.last_diagnostics = {}

    def build_many(self, contexts, *, item_concurrency=1, item_batch_size=3):
        item_summaries = [
            InsightSummary(
                kind="item",
                key=f"item:{context.news_item_id}",
                title=context.title,
                summary=f"{context.title} summary",
                item_ids=[context.news_item_id],
                evidence_topics=list(context.evidence_topics),
                sources=[context.source],
            )
            for context in contexts
        ]
        report_summary = InsightSummary(
            kind="report",
            key="report",
            title="报告摘要",
            summary="Report summary.",
            item_ids=[item_id for summary in item_summaries for item_id in summary.item_ids],
        )
        bundle = InsightSummaryBundle(item_summaries=item_summaries, report_summary=report_summary)
        self.last_diagnostics = {
            "summary_count": len(bundle.summaries),
            "item_summary_count": len(item_summaries),
            "item_summary_failed_count": 0,
            "report_summary_present": True,
            "summary_model_calls": len(item_summaries) + 1,
            "summary_concurrency": item_concurrency,
            "summary_batch_size": item_batch_size,
        }
        return bundle


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
            summary_builder=StubSummaryBuilder(),
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
        self.assertEqual(len(result.diagnostics["reduced_contexts"]), 2)
        self.assertEqual(len(result.diagnostics["item_summary_payloads"]), 2)
        self.assertNotIn("theme_summary_payloads", result.diagnostics)
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
