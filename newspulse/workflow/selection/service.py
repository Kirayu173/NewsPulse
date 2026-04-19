# coding=utf-8
"""Selection stage service."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.keyword import KeywordSelectionStrategy
from newspulse.workflow.shared.contracts import SelectionResult
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
        embedding_runtime_config: dict[str, Any] | None = None,
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
                embedding_runtime_config=embedding_runtime_config,
                filter_config=ai_filter_config,
                config_root=config_root,
                debug=debug,
            )

    def run(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        """Run the configured selection strategy."""

        requested_strategy = options.strategy
        try:
            result = self._run_strategy(snapshot, options)
        except Exception as exc:
            if requested_strategy == "ai" and options.ai.fallback_to_keyword:
                fallback_options = replace(options, strategy="keyword")
                result = self._run_strategy(snapshot, fallback_options)
                result.diagnostics.update(
                    {
                        "requested_strategy": "ai",
                        "fallback_strategy": "keyword",
                        "fallback_reason": f"{type(exc).__name__}: {exc}",
                    }
                )
            else:
                raise

        result.selected_new_items = result.resolve_selected_new_items(
            getattr(snapshot, "new_items", []),
        )
        result.diagnostics.setdefault("requested_strategy", requested_strategy)
        return result

    def _run_strategy(self, snapshot: Any, options: SelectionOptions) -> SelectionResult:
        if options.strategy == "keyword":
            return self.keyword_strategy.run(snapshot, options)
        if options.strategy == "ai":
            if self.ai_strategy is None:
                raise NotImplementedError("AI selection strategy is not configured")
            return self.ai_strategy.run(snapshot, options)
        raise NotImplementedError(f"Unsupported selection strategy: {options.strategy}")
