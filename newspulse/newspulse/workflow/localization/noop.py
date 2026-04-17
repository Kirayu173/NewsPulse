# coding=utf-8
"""No-op localization strategy."""

from __future__ import annotations

from newspulse.workflow.shared.contracts import LocalizedReport, RenderableReport
from newspulse.workflow.shared.options import LocalizationOptions


class NoopLocalizationStrategy:
    """Return the original report without any localization."""

    def run(self, report: RenderableReport, options: LocalizationOptions) -> LocalizedReport:
        return LocalizedReport(
            base_report=report,
            language=options.language,
            translation_meta={
                "enabled": False,
                "strategy": "noop",
                "skipped": True,
                "reason": "localization stage disabled",
            },
        )
