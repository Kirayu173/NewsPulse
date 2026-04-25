# coding=utf-8
"""AI-based lightweight native insight workflow."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from newspulse.workflow.insight.aggregate import InsightAggregateGenerator
from newspulse.workflow.insight.brief_builder import InsightBriefBuilder
from newspulse.workflow.insight.input_builder import InsightInputBuilder
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient, CachedAIRuntimeClient
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.ai_runtime.request_config import resolve_runtime_cache_config
from newspulse.workflow.shared.contracts import InsightResult
from newspulse.workflow.shared.options import InsightOptions


class AIInsightStrategy:
    """Run the native stage-5 pipeline: context -> brief -> aggregate."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        storage_manager: Any | None = None,
        proxy_url: str | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        input_builder: InsightInputBuilder | None = None,
        brief_builder: InsightBriefBuilder | None = None,
        aggregate_generator: InsightAggregateGenerator | None = None,
    ):
        del storage_manager, proxy_url
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        shared_client = client
        if shared_client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            shared_client = AIRuntimeClient(ai_runtime_config)
        shared_client = self._wrap_runtime_cache(shared_client)
        self.shared_client = shared_client

        self.input_builder = input_builder or InsightInputBuilder()
        self.brief_builder = brief_builder or InsightBriefBuilder()
        self.aggregate_generator = aggregate_generator or InsightAggregateGenerator(
            ai_runtime_config=ai_runtime_config,
            analysis_config=self.analysis_config,
            config_root=self.config_root,
            client=shared_client,
            prompt_template=prompt_template,
        )

    def run(self, snapshot: Any, selection: Any, options: InsightOptions) -> InsightResult:
        contexts = []
        briefs = []
        raw_response = ""
        cache_stats_before = self._cache_stats()
        try:
            contexts = self.input_builder.build(snapshot, selection, max_items=options.max_items)
            if not contexts:
                return InsightResult(
                    enabled=True,
                    strategy="ai",
                    diagnostics=self._build_diagnostics(
                        snapshot=snapshot,
                        selection=selection,
                        options=options,
                        contexts=contexts,
                        briefs=briefs,
                        aggregate_diag={"skipped": True, "reason": "no selected items available for insight generation"},
                        cache_stats=self._cache_delta(cache_stats_before),
                        skipped=True,
                        reason="no selected items available for insight generation",
                    ),
                )

            briefs = self.brief_builder.build_many(contexts)
            if not briefs:
                return InsightResult(
                    enabled=True,
                    strategy="ai",
                    diagnostics=self._build_diagnostics(
                        snapshot=snapshot,
                        selection=selection,
                        options=options,
                        contexts=contexts,
                        briefs=briefs,
                        aggregate_diag={"skipped": True, "reason": "no briefs available for insight generation"},
                        cache_stats=self._cache_delta(cache_stats_before),
                        skipped=True,
                        reason="no briefs available for insight generation",
                    ),
                )

            sections, raw_response, aggregate_diag = self.aggregate_generator.generate(briefs, contexts)
            return InsightResult(
                enabled=True,
                strategy="ai",
                sections=list(sections),
                briefs=list(briefs),
                raw_response=raw_response,
                diagnostics=self._build_diagnostics(
                    snapshot=snapshot,
                    selection=selection,
                    options=options,
                    contexts=contexts,
                    briefs=briefs,
                    aggregate_diag=aggregate_diag,
                    cache_stats=self._cache_delta(cache_stats_before),
                ),
            )
        except Exception as exc:
            return InsightResult(
                enabled=True,
                strategy="ai",
                briefs=list(briefs),
                raw_response=raw_response,
                diagnostics=self._build_diagnostics(
                    snapshot=snapshot,
                    selection=selection,
                    options=options,
                    contexts=contexts,
                    briefs=briefs,
                    aggregate_diag={"error": f"{type(exc).__name__}: {exc}"},
                    cache_stats=self._cache_delta(cache_stats_before),
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )

    def _runtime_cache_config(self) -> dict[str, Any]:
        return resolve_runtime_cache_config(self.analysis_config)

    def _wrap_runtime_cache(self, client: AIRuntimeClient | Any) -> AIRuntimeClient | Any:
        if isinstance(client, CachedAIRuntimeClient):
            return client
        if not isinstance(client, AIRuntimeClient):
            return client
        cache_config = self._runtime_cache_config()
        return CachedAIRuntimeClient(
            client,
            enabled=bool(cache_config.get("ENABLED", True)),
            ttl_seconds=int(cache_config.get("TTL_SECONDS", 3600) or 3600),
            max_entries=int(cache_config.get("MAX_ENTRIES", 512) or 512),
        )

    def _cache_stats(self) -> dict[str, Any]:
        cache_stats = getattr(self.shared_client, "cache_stats", None)
        if callable(cache_stats):
            return dict(cache_stats())
        return {"enabled": False, "entries": 0, "hits": 0, "misses": 0}

    def _cache_delta(self, before: Mapping[str, Any]) -> dict[str, Any]:
        after = self._cache_stats()
        return {
            "enabled": after.get("enabled", False),
            "entries": int(after.get("entries", 0) or 0),
            "hits": max(0, int(after.get("hits", 0) or 0) - int(before.get("hits", 0) or 0)),
            "misses": max(0, int(after.get("misses", 0) or 0) - int(before.get("misses", 0) or 0)),
        }

    def _build_diagnostics(
        self,
        *,
        snapshot: Any,
        selection: Any,
        options: InsightOptions,
        contexts: list[Any],
        briefs: list[Any],
        aggregate_diag: Mapping[str, Any],
        cache_stats: Mapping[str, Any],
        skipped: bool = False,
        reason: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        diagnostics = {
            "mode": getattr(snapshot, "mode", ""),
            "report_mode": options.mode,
            "selected_items": int(getattr(selection, "total_selected", len(getattr(selection, "selected_items", []) or [])) or 0),
            "brief_count": len(briefs),
            "section_count": int(aggregate_diag.get("section_count", 0) or 0),
            "max_items": options.max_items,
            "llm_cache_enabled": bool(cache_stats.get("enabled", False)),
            "llm_cache_hits": int(cache_stats.get("hits", 0) or 0),
            "llm_cache_misses": int(cache_stats.get("misses", 0) or 0),
            "llm_cache_entries": int(cache_stats.get("entries", 0) or 0),
            "input_contexts": [asdict(context) for context in contexts],
            "brief_payloads": [asdict(brief) for brief in briefs],
            "aggregate": dict(aggregate_diag or {}),
        }
        if skipped:
            diagnostics["skipped"] = True
        if reason:
            diagnostics["reason"] = reason
        if error:
            diagnostics["error"] = error
        return diagnostics
