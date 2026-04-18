# coding=utf-8
"""Insight stage service."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.noop import NoopInsightStrategy
from newspulse.workflow.shared.options import InsightOptions


class InsightService:
    """Dispatch insight strategies for the native workflow pipeline."""

    def __init__(
        self,
        *,
        ai_strategy: AIInsightStrategy | None = None,
        noop_strategy: NoopInsightStrategy | None = None,
        ai_runtime_config: dict[str, Any] | None = None,
        ai_analysis_config: dict[str, Any] | None = None,
        config_root: str | None = None,
    ):
        self.noop_strategy = noop_strategy or NoopInsightStrategy()
        self.ai_strategy = ai_strategy
        if self.ai_strategy is None and ai_runtime_config is not None:
            self.ai_strategy = AIInsightStrategy(
                ai_runtime_config=ai_runtime_config,
                analysis_config=ai_analysis_config,
                config_root=config_root,
            )

    def run(self, snapshot: Any, selection: Any, options: InsightOptions):
        """Run the configured insight strategy."""

        if not options.enabled or options.strategy == "noop":
            return self.noop_strategy.run(snapshot, selection, options)
        if options.strategy == "ai":
            if self.ai_strategy is None:
                raise NotImplementedError("AI insight strategy is not configured")
            return self.ai_strategy.run(snapshot, selection, options)
        raise NotImplementedError(f"Unsupported insight strategy: {options.strategy}")
