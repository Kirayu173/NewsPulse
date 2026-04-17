# coding=utf-8
"""No-op insight strategy."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.shared.contracts import InsightResult
from newspulse.workflow.shared.options import InsightOptions


class NoopInsightStrategy:
    """Return an empty insight result while preserving stage diagnostics."""

    def run(self, snapshot: Any, selection: Any, options: InsightOptions) -> InsightResult:
        return InsightResult(
            enabled=False,
            strategy="noop",
            diagnostics={
                "mode": snapshot.mode,
                "requested_strategy": options.strategy,
                "selection_strategy": selection.strategy,
                "selected_items": selection.total_selected,
                "skipped": True,
            },
        )
