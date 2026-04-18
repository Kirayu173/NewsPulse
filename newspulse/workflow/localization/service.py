# coding=utf-8
"""Localization stage service."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.localization.ai import AILocalizationStrategy
from newspulse.workflow.localization.noop import NoopLocalizationStrategy
from newspulse.workflow.shared.options import LocalizationOptions


class LocalizationService:
    """Dispatch localization strategies for the native workflow pipeline."""

    def __init__(
        self,
        *,
        ai_strategy: AILocalizationStrategy | None = None,
        noop_strategy: NoopLocalizationStrategy | None = None,
        ai_translation_config: dict[str, Any] | None = None,
        ai_runtime_config: dict[str, Any] | None = None,
        config_root: str | None = None,
    ):
        self.noop_strategy = noop_strategy or NoopLocalizationStrategy()
        self.ai_strategy = ai_strategy
        if self.ai_strategy is None and ai_translation_config is not None:
            self.ai_strategy = AILocalizationStrategy(
                translation_config=ai_translation_config,
                ai_runtime_config=ai_runtime_config,
                config_root=config_root,
            )

    def run(self, report: Any, options: LocalizationOptions):
        """Run the configured localization strategy."""

        if not options.enabled or options.strategy == "noop":
            return self.noop_strategy.run(report, options)
        if options.strategy == "ai":
            if self.ai_strategy is None:
                raise NotImplementedError("AI localization strategy is not configured")
            return self.ai_strategy.run(report, options)
        raise NotImplementedError(f"Unsupported localization strategy: {options.strategy}")
