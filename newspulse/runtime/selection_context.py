# coding=utf-8
"""Selection-stage option builder."""

from __future__ import annotations

from newspulse.runtime.settings import RuntimeSettings
from newspulse.workflow.shared.options import SelectionAIOptions, SelectionOptions, SelectionSemanticOptions


class SelectionOptionsBuilder:
    """Build selection options from runtime settings."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    def build(
        self,
        *,
        strategy: str | None = None,
        frequency_file: str | None = None,
        interests_file: str | None = None,
    ) -> SelectionOptions:
        stage = self.settings.selection
        return SelectionOptions(
            strategy=strategy or stage.strategy,
            frequency_file=frequency_file or stage.frequency_file,
            priority_sort_enabled=stage.priority_sort_enabled,
            ai=SelectionAIOptions(
                interests_file=interests_file or stage.ai.interests_file or "ai_interests.txt",
                batch_size=stage.ai.batch_size,
                batch_interval=stage.ai.batch_interval,
                min_score=stage.ai.min_score,
                fallback_to_keyword=stage.ai.fallback_to_keyword,
            ),
            semantic=SelectionSemanticOptions(
                enabled=stage.semantic.enabled,
                top_k=stage.semantic.top_k,
                min_score=stage.semantic.min_score,
                direct_threshold=stage.semantic.direct_threshold,
            ),
        )
