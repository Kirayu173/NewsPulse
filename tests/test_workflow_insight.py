import unittest

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.service import InsightService
from newspulse.workflow.insight.models import (
    InsightBrief,
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
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


class StubBriefBuilder:
    def build_many(self, contexts):
        return [
            InsightBrief(
                news_item_id=context.news_item_id,
                title=context.title,
                source_id=context.source_id,
                source_name=context.source_name,
                source_kind=context.source_context.source_kind,
                summary=context.source_context.summary,
                matched_topics=context.selection_evidence.matched_topics,
                quality_score=context.selection_evidence.quality_score,
                current_rank=context.rank_signals.current_rank,
                rank_trend=context.rank_signals.rank_trend,
                url=context.url,
            )
            for context in contexts
        ]


class StubAggregate:
    def generate(self, briefs, contexts):
        return (
            [
                InsightSection(
                    key="core_trends",
                    title="Core Trends",
                    content="终端代理与开源项目同时升温。",
                    metadata={"supporting_news_ids": [brief.news_item_id for brief in briefs]},
                )
            ],
            '{"sections": []}',
            {"brief_count": len(briefs), "section_count": 1},
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
        self.assertEqual(result.briefs, [])
        self.assertTrue(result.diagnostics["skipped"])

    def test_ai_strategy_runs_lightweight_pipeline_and_emits_brief_payloads(self):
        snapshot = HotlistSnapshot(mode="current", generated_at="2026-04-20 10:00:00")
        selection = SelectionResult(strategy="ai", total_selected=2)
        strategy = AIInsightStrategy(
            client=object(),
            input_builder=StubInputBuilder(),
            brief_builder=StubBriefBuilder(),
            aggregate_generator=StubAggregate(),
            analysis_config={},
        )
        service = InsightService(ai_strategy=strategy)

        result = service.run(snapshot, selection, InsightOptions(enabled=True, strategy="ai", mode="current", max_items=2))

        self.assertTrue(result.enabled)
        self.assertEqual(result.strategy, "ai")
        self.assertEqual(len(result.briefs), 2)
        self.assertEqual(result.sections[0].metadata["supporting_news_ids"], ["1", "2"])
        self.assertEqual(result.diagnostics["brief_count"], 2)
        self.assertFalse(result.diagnostics["llm_cache_enabled"])
        self.assertEqual(result.diagnostics["llm_cache_hits"], 0)
        self.assertEqual(result.diagnostics["llm_cache_misses"], 0)
        self.assertEqual(len(result.diagnostics["input_contexts"]), 2)
        self.assertEqual(len(result.diagnostics["brief_payloads"]), 2)
        self.assertNotIn("item_analysis_payloads", result.diagnostics)
        self.assertNotIn("content_payloads", result.diagnostics)
        self.assertNotIn("reduced_bundles", result.diagnostics)

    def test_service_raises_for_unknown_strategy(self):
        snapshot = HotlistSnapshot(mode="current", generated_at="2026-04-20 10:00:00")
        selection = SelectionResult(strategy="keyword")
        service = InsightService()

        with self.assertRaises(NotImplementedError):
            service.run(snapshot, selection, InsightOptions(enabled=True, strategy="custom"))


if __name__ == "__main__":
    unittest.main()
