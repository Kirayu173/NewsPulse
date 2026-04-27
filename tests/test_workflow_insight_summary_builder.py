import unittest

from newspulse.workflow.insight.content_models import ReducedSummaryContext
from newspulse.workflow.insight.summary_builder import InsightSummaryBuilder
from newspulse.workflow.shared.contracts import InsightSummary


class StubItemSummaryGenerator:
    def generate_many(self, contexts, *, max_workers=1, batch_size=3):
        summaries = [
            InsightSummary(
                kind="item",
                key=f"item:{context.news_item_id}",
                title=context.title,
                summary=f"{context.title} summary",
                item_ids=[context.news_item_id],
                evidence_topics=list(context.evidence_topics),
                evidence_notes=list(context.evidence_notes),
                sources=[context.source],
                metadata={"quality_score": 0.9, "current_rank": index + 1},
            )
            for index, context in enumerate(contexts)
        ]
        return summaries, {
            "summary_model_calls": 1,
            "summary_concurrency": max_workers,
            "summary_batch_size": batch_size,
            "summary_batch_count": 1,
            "item_summary_count": len(summaries),
            "item_summary_failed_count": 0,
        }


class StubReportSummaryGenerator:
    def __init__(self):
        self.item_summaries = []

    def generate(self, item_summaries, *, failed_item_summary_count=0):
        self.item_summaries = list(item_summaries)
        report = InsightSummary(
            kind="report",
            key="report",
            title="报告摘要",
            summary="Two item summaries were synthesized into a report summary.",
            item_ids=[item_id for summary in item_summaries for item_id in summary.item_ids],
            evidence_topics=["AI"],
            sources=["Hacker News"],
            metadata={
                "item_summary_count": len(item_summaries),
                "failed_item_summary_count": failed_item_summary_count,
            },
        )
        return report, '{"summary": "ok"}', {"report_summary_present": True}


class InsightSummaryBuilderTest(unittest.TestCase):
    def test_build_many_creates_item_and_report_summaries_only(self):
        report_generator = StubReportSummaryGenerator()
        builder = InsightSummaryBuilder(
            item_summary_generator=StubItemSummaryGenerator(),
            report_summary_generator=report_generator,
        )
        contexts = [
            ReducedSummaryContext(
                news_item_id="1",
                title="OpenAI launches a coding agent",
                source="Hacker News",
                url="https://example.com/1",
                evidence_topics=["AI"],
                evidence_notes=["developer workflow"],
            ),
            ReducedSummaryContext(
                news_item_id="2",
                title="GitHub ships MCP toolkit",
                source="GitHub Trending",
                url="https://example.com/2",
                evidence_topics=["Open Source"],
            ),
        ]

        bundle = builder.build_many(contexts, item_concurrency=3)

        self.assertEqual([summary.kind for summary in bundle.summaries], ["report", "item", "item"])
        self.assertEqual(len(bundle.item_summaries), 2)
        self.assertIsNotNone(bundle.report_summary)
        self.assertEqual(report_generator.item_summaries, bundle.item_summaries)
        self.assertEqual(builder.last_diagnostics["item_summary_count"], 2)
        self.assertEqual(builder.last_diagnostics["summary_concurrency"], 3)
        self.assertEqual(builder.last_diagnostics["report_summary_payload"]["kind"], "report")
        self.assertNotIn("theme_summary_payloads", builder.last_diagnostics)

    def test_summary_contract_rejects_theme_kind(self):
        with self.assertRaises(ValueError):
            InsightSummary(kind="theme", key="theme:x", title="X", summary="legacy")


if __name__ == "__main__":
    unittest.main()
