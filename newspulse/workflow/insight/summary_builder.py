# coding=utf-8
"""Build item and report summaries from reduced item contexts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from newspulse.workflow.insight.content_models import ReducedSummaryContext
from newspulse.workflow.insight.item_summary_generator import ItemSummaryGenerator
from newspulse.workflow.insight.report_summary_generator import ReportSummaryGenerator
from newspulse.workflow.shared.contracts import InsightSummaryBundle


class InsightSummaryBuilder:
    """Orchestrate item-summary-first generation without theme summaries."""

    def __init__(
        self,
        *,
        item_summary_generator: ItemSummaryGenerator | Any,
        report_summary_generator: ReportSummaryGenerator | Any,
    ):
        self.item_summary_generator = item_summary_generator
        self.report_summary_generator = report_summary_generator
        self.last_raw_report_response = ""
        self.last_diagnostics: dict[str, Any] = {}

    def build_many(
        self,
        contexts: Sequence[ReducedSummaryContext],
        *,
        item_concurrency: int = 1,
    ) -> InsightSummaryBundle:
        item_summaries, item_diag = self.item_summary_generator.generate_many(
            contexts,
            max_workers=item_concurrency,
        )
        report_summary, raw_report, report_diag = self.report_summary_generator.generate(
            item_summaries,
            failed_item_summary_count=int(item_diag.get("item_summary_failed_count", 0) or 0),
        )
        bundle = InsightSummaryBundle(
            item_summaries=list(item_summaries),
            report_summary=report_summary,
        )
        self.last_raw_report_response = raw_report
        self.last_diagnostics = {
            "summary_count": len(bundle.summaries),
            "item_summary_count": len(item_summaries),
            "item_summary_failed_count": int(item_diag.get("item_summary_failed_count", 0) or 0),
            "report_summary_present": report_summary is not None,
            "summary_model_calls": int(item_diag.get("summary_model_calls", 0) or 0)
            + (1 if report_summary is not None else 0),
            "summary_concurrency": int(item_diag.get("summary_concurrency", item_concurrency) or item_concurrency),
            "item": dict(item_diag),
            "report": dict(report_diag),
            "summary_payloads": [asdict(summary) for summary in bundle.summaries],
            "item_summary_payloads": [asdict(summary) for summary in item_summaries],
            "report_summary_payload": asdict(report_summary) if report_summary is not None else {},
        }
        return bundle
