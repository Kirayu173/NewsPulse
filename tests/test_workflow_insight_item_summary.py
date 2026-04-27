import json
import time
import unittest
from pathlib import Path

from newspulse.workflow.insight.content_models import ReducedSummaryContext
from newspulse.workflow.insight.item_summary_generator import ItemSummaryGenerator
from newspulse.workflow.insight.report_summary_generator import ReportSummaryGenerator
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import InsightSummary
from tests.helpers.runtime import json_result


class EchoItemClient:
    def __init__(self, *, fail_item_id: str = ""):
        self.fail_item_id = fail_item_id
        self.calls = []

    def generate_json(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        rows = json.loads(prompt)
        if any(row["news_item_id"] == self.fail_item_id for row in rows):
            raise RuntimeError("model failed")
        if any(row["news_item_id"] == "1" for row in rows):
            time.sleep(0.03)
        return json_result(
            {
                "items": [
                    {
                        "news_item_id": row["news_item_id"],
                        "summary": f"{row['title']} model summary",
                        "evidence_notes": ["model note"],
                        "quality_score": 0.91,
                    }
                    for row in rows
                ]
            }
        )


class RecordingReportClient:
    def __init__(self):
        self.calls = []

    def generate_json(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        return json_result({"title": "报告摘要", "summary": "Report based only on item summaries."})


def _context(item_id: str, title: str) -> ReducedSummaryContext:
    return ReducedSummaryContext(
        news_item_id=item_id,
        title=title,
        source="Hacker News",
        url=f"https://example.com/{item_id}",
        source_summary="source summary",
        key_paragraphs=["paragraph evidence"],
        evidence_topics=["AI"],
        evidence_notes=["selection note"],
        rank_signals={"current_rank": int(item_id), "quality_score": 0.8},
        metadata={"source_id": "hackernews"},
    )


class ItemSummaryGeneratorTest(unittest.TestCase):
    def test_generate_many_preserves_input_order_under_concurrency(self):
        client = EchoItemClient()
        generator = ItemSummaryGenerator(
            client=client,
            analysis_config={"LANGUAGE": "Chinese"},
            summary_config={"ITEM_SUMMARY_MAX_CHARS": 220},
            prompt_template=PromptTemplate(path=Path("item.txt"), user_prompt="{item_contexts_json}"),
        )

        summaries, diagnostics = generator.generate_many(
            [_context("1", "First"), _context("2", "Second")],
            max_workers=2,
        )

        self.assertEqual([summary.item_ids[0] for summary in summaries], ["1", "2"])
        self.assertEqual([summary.kind for summary in summaries], ["item", "item"])
        self.assertEqual(summaries[0].summary, "First model summary")
        self.assertEqual(summaries[0].metadata["reduced_context_chars"], len("paragraph evidence"))
        self.assertEqual(diagnostics["item_summary_failed_count"], 0)
        self.assertEqual(diagnostics["summary_model_calls"], 1)
        self.assertEqual(diagnostics["summary_batch_size"], 3)
        self.assertEqual(diagnostics["summary_concurrency"], 2)

    def test_generate_many_records_per_item_failures_without_fallback_summary(self):
        generator = ItemSummaryGenerator(
            client=EchoItemClient(fail_item_id="2"),
            analysis_config={},
            summary_config={},
            prompt_template=PromptTemplate(path=Path("item.txt"), user_prompt="{item_contexts_json}"),
        )

        summaries, diagnostics = generator.generate_many(
            [_context("1", "First"), _context("2", "Second")],
            max_workers=2,
        )

        self.assertEqual(summaries, [])
        self.assertEqual(diagnostics["item_summary_failed_count"], 2)
        self.assertEqual([failure["news_item_id"] for failure in diagnostics["failures"]], ["1", "2"])

    def test_generate_many_batches_four_items_into_two_model_calls(self):
        client = EchoItemClient()
        generator = ItemSummaryGenerator(
            client=client,
            analysis_config={},
            summary_config={},
            prompt_template=PromptTemplate(path=Path("item.txt"), user_prompt="{item_contexts_json}"),
        )

        summaries, diagnostics = generator.generate_many(
            [
                _context("1", "First"),
                _context("2", "Second"),
                _context("3", "Third"),
                _context("4", "Fourth"),
            ],
            max_workers=2,
            batch_size=3,
        )

        self.assertEqual([summary.item_ids[0] for summary in summaries], ["1", "2", "3", "4"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(diagnostics["summary_model_calls"], 2)
        self.assertEqual(diagnostics["summary_batch_count"], 2)


class ReportSummaryGeneratorTest(unittest.TestCase):
    def test_report_summary_prompt_consumes_only_item_summary_payloads(self):
        client = RecordingReportClient()
        generator = ReportSummaryGenerator(
            client=client,
            analysis_config={"LANGUAGE": "Chinese"},
            summary_config={"REPORT_SUMMARY_MAX_CHARS": 300},
            prompt_template=PromptTemplate(path=Path("report.txt"), user_prompt="{item_summaries_json}"),
        )
        item_summary = InsightSummary(
            kind="item",
            key="item:1",
            title="First",
            summary="First item summary.",
            item_ids=["1"],
            evidence_topics=["AI"],
            sources=["Hacker News"],
            metadata={"quality_score": 0.9, "current_rank": 1},
        )

        report, raw, diagnostics = generator.generate([item_summary], failed_item_summary_count=1)

        self.assertIsNotNone(report)
        self.assertEqual(report.kind, "report")
        self.assertEqual(report.metadata["item_summary_count"], 1)
        self.assertEqual(report.metadata["failed_item_summary_count"], 1)
        self.assertIn("First item summary.", client.calls[0])
        self.assertNotIn("key_paragraphs", client.calls[0])
        self.assertTrue(raw)
        self.assertTrue(diagnostics["report_summary_present"])

    def test_report_summary_skips_when_no_item_summaries_exist(self):
        generator = ReportSummaryGenerator(
            client=RecordingReportClient(),
            analysis_config={},
            summary_config={},
            prompt_template=PromptTemplate(path=Path("report.txt"), user_prompt="{item_summaries_json}"),
        )

        report, raw, diagnostics = generator.generate([])

        self.assertIsNone(report)
        self.assertEqual(raw, "")
        self.assertTrue(diagnostics["skipped"])


if __name__ == "__main__":
    unittest.main()
