import unittest
from datetime import datetime
from pathlib import Path

from tests.helpers.tempdir import WorkspaceTemporaryDirectory as TemporaryDirectory

from newspulse.workflow.insight.review import export_insight_outbox
from newspulse.workflow.shared.contracts import (
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    InsightSummary,
    SelectionResult,
)


class InsightReviewExportTest(unittest.TestCase):
    def test_export_writes_stage5_artifacts(self):
        with TemporaryDirectory() as tmp:
            snapshot = HotlistSnapshot(
                mode="current",
                generated_at="2026-04-20 10:00:00",
                items=[HotlistItem(news_item_id="1", source_id="hackernews", title="A")],
            )
            selection = SelectionResult(
                strategy="ai",
                selected_items=list(snapshot.items),
                total_candidates=1,
                total_selected=1,
            )
            insight = InsightResult(
                enabled=True,
                strategy="ai",
                sections=[
                    InsightSection(
                        key="core_trends",
                        title="Core Trends",
                        content="Trend summary.",
                        metadata={"supporting_news_ids": ["1"]},
                    )
                ],
                summaries=[
                    InsightSummary(
                        kind="item",
                        key="item:1",
                        title="A",
                        summary="summary",
                        item_ids=["1"],
                        theme_keys=["theme:ai"],
                        evidence_topics=["AI"],
                        sources=["Hacker News"],
                    )
                ],
                diagnostics={
                    "input_contexts": [{"news_item_id": "1", "title": "A"}],
                    "summary_payloads": [
                        {
                            "kind": "item",
                            "key": "item:1",
                            "title": "A",
                            "summary": "summary",
                            "item_ids": ["1"],
                            "evidence_topics": ["AI"],
                        }
                    ],
                    "item_summary_payloads": [
                        {
                            "kind": "item",
                            "key": "item:1",
                            "title": "A",
                            "summary": "summary",
                            "item_ids": ["1"],
                            "evidence_topics": ["AI"],
                        }
                    ],
                    "theme_summary_payloads": [],
                    "report_summary_payload": {},
                    "aggregate": {"summary_count": 1, "section_count": 1},
                },
            )

            summary = export_insight_outbox(
                outbox_dir=tmp,
                generated_at=datetime(2026, 4, 20, 10, 0, 0),
                config_path="config/config.yaml",
                storage_data_dir="output/test",
                snapshot=snapshot,
                selection=selection,
                insight=insight,
                run_log="ok",
            )

            self.assertEqual(summary["insight"]["section_count"], 1)
            self.assertEqual(summary["insight"]["summary_count"], 1)
            for filename in (
                "stage5_summary_input.json",
                "stage5_summaries.json",
                "stage5_global_insight.json",
                "stage5_summary_review.md",
                "stage5_global_insight_review.md",
            ):
                self.assertTrue((Path(tmp) / filename).exists(), filename)
            self.assertFalse((Path(tmp) / ("stage5_" + "insight_" + "briefs.json")).exists())
            self.assertFalse((Path(tmp) / ("stage5_item_" + "analysis.json")).exists())


if __name__ == "__main__":
    unittest.main()
