# coding=utf-8
"""Selection stage service."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.keyword import KeywordSelectionStrategy
from newspulse.workflow.shared.options import SelectionOptions


class SelectionService:
    """Dispatch selection strategies for the workflow pipeline."""

    def __init__(
        self,
        *,
        config_root: str | None = None,
        rank_threshold: int = 50,
        weight_config: dict[str, float] | None = None,
        max_news_per_keyword: int = 0,
        sort_by_position_first: bool = False,
        keyword_strategy: KeywordSelectionStrategy | None = None,
        ai_strategy: AISelectionStrategy | None = None,
        storage_manager: Any | None = None,
        ai_runtime_config: dict[str, Any] | None = None,
        ai_filter_config: dict[str, Any] | None = None,
        debug: bool = False,
    ):
        self.keyword_strategy = keyword_strategy or KeywordSelectionStrategy(
            config_root=config_root,
            rank_threshold=rank_threshold,
            weight_config=weight_config,
            max_news_per_keyword=max_news_per_keyword,
            sort_by_position_first=sort_by_position_first,
        )
        self.ai_strategy = ai_strategy
        if self.ai_strategy is None and storage_manager is not None and ai_runtime_config is not None:
            self.ai_strategy = AISelectionStrategy(
                storage_manager=storage_manager,
                ai_runtime_config=ai_runtime_config,
                filter_config=ai_filter_config,
                config_root=config_root,
                debug=debug,
            )

    def run(self, snapshot: Any, options: SelectionOptions):
        """Run the configured selection strategy."""

        if options.strategy == "keyword":
            result = self.keyword_strategy.run(snapshot, options)
            result.selected_new_items = result.resolve_selected_new_items(getattr(snapshot, "new_items", []))
            return result
        if options.strategy == "ai":
            if self.ai_strategy is None:
                raise NotImplementedError("AI selection strategy is not configured")
            result = self.ai_strategy.run(snapshot, options)
            result.selected_new_items = result.resolve_selected_new_items(getattr(snapshot, "new_items", []))
            return result
        raise NotImplementedError(f"Unsupported selection strategy: {options.strategy}")
