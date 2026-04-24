# coding=utf-8
"""Insight-stage option builder."""

from __future__ import annotations

from newspulse.runtime.settings import RuntimeSettings
from newspulse.workflow.shared.options import InsightOptions


class InsightOptionsBuilder:
    """Build insight options from runtime settings."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    def build(self, *, report_mode: str) -> InsightOptions:
        stage = self.settings.insight
        requested_mode = str(stage.analysis_config.get("MODE", stage.mode) or stage.mode).strip()
        effective_mode = report_mode
        return InsightOptions(
            enabled=stage.enabled,
            strategy=stage.strategy,
            mode=effective_mode,
            max_items=stage.max_items,
            metadata={
                "requested_mode": requested_mode,
                "report_mode": report_mode,
                "mode_resolved_by_context": requested_mode != report_mode,
            },
        )
