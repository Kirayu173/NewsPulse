# coding=utf-8
"""AI-based native insight workflow."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from newspulse.workflow.insight.aggregate import InsightAggregateGenerator
from newspulse.workflow.insight.content_fetcher import InsightContentFetcher
from newspulse.workflow.insight.content_reducer import InsightContentReducer
from newspulse.workflow.insight.input_builder import InsightInputBuilder
from newspulse.workflow.insight.item_analyzer import InsightItemAnalyzer
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient, CachedAIRuntimeClient
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.ai_runtime.request_config import resolve_runtime_cache_config
from newspulse.workflow.shared.contracts import InsightResult
from newspulse.workflow.shared.options import InsightOptions


class AIInsightStrategy:
    """Run the native stage-5 pipeline: context -> content -> item analysis -> aggregate."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        storage_manager: Any | None = None,
        proxy_url: str | None = None,
        client: AIRuntimeClient | Any | None = None,
        completion_func: Callable[..., Any] | None = None,
        prompt_template: PromptTemplate | None = None,
        item_prompt_template: PromptTemplate | None = None,
        input_builder: InsightInputBuilder | None = None,
        content_fetcher: InsightContentFetcher | None = None,
        content_reducer: InsightContentReducer | None = None,
        item_analyzer: InsightItemAnalyzer | None = None,
        aggregate_generator: InsightAggregateGenerator | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        shared_client = client
        if shared_client is None:
            if ai_runtime_config is None:
                raise ValueError('AI runtime config is required when no client is provided')
            shared_client = AIRuntimeClient(ai_runtime_config, completion_func=completion_func)
        shared_client = self._wrap_runtime_cache(shared_client)
        self.shared_client = shared_client

        content_config = self._content_config()
        item_config = self._item_config()
        aggregate_config = self._aggregate_config()

        self.input_builder = input_builder or InsightInputBuilder()
        self.content_fetcher = content_fetcher or InsightContentFetcher(
            storage_manager=storage_manager,
            timeout=int(content_config.get('REQUEST_TIMEOUT', content_config.get('TIMEOUT', 12)) or 12),
            proxy_url=proxy_url,
            cache_enabled=bool(content_config.get('CACHE_ENABLED', True)),
            async_enabled=bool(content_config.get('ASYNC_ENABLED', False)),
            max_concurrency=int(content_config.get('MAX_CONCURRENCY', 1) or 1),
            request_timeout=int(content_config.get('REQUEST_TIMEOUT', content_config.get('TIMEOUT', 12)) or 12),
        )
        self.content_reducer = content_reducer or InsightContentReducer(
            reduced_chars=int(content_config.get('REDUCED_CHARS', 1600) or 1600),
            evidence_sentences=int(item_config.get('MIN_EVIDENCE_SENTENCES', 3) or 3),
        )
        self.item_analyzer = item_analyzer or InsightItemAnalyzer(
            ai_runtime_config=ai_runtime_config,
            analysis_config={**self.analysis_config, **item_config},
            config_root=self.config_root,
            client=shared_client,
            prompt_template=item_prompt_template,
            completion_func=completion_func,
        )
        self.aggregate_generator = aggregate_generator or InsightAggregateGenerator(
            ai_runtime_config=ai_runtime_config,
            analysis_config={**self.analysis_config, **aggregate_config},
            config_root=self.config_root,
            client=shared_client,
            prompt_template=prompt_template,
            completion_func=completion_func,
        )

    def run(self, snapshot: Any, selection: Any, options: InsightOptions) -> InsightResult:
        contexts = []
        content_payloads = []
        reduced_bundles = []
        item_analyses = []
        raw_response = ''
        content_config = self._content_config()
        cache_stats_before = self._cache_stats()
        try:
            contexts = self.input_builder.build(snapshot, selection, max_items=options.max_items)
            if not contexts:
                cache_stats = self._cache_delta(cache_stats_before)
                return InsightResult(
                    enabled=True,
                    strategy='ai',
                    diagnostics={
                        'mode': snapshot.mode,
                        'report_mode': options.mode,
                        'selected_items': getattr(selection, 'total_selected', 0),
                        'analyzed_items': 0,
                        'max_items': options.max_items,
                        'skipped': True,
                        'reason': 'no selected items available for insight generation',
                        'llm_cache_enabled': bool(cache_stats.get('enabled', False)),
                        'llm_cache_hits': int(cache_stats.get('hits', 0)),
                        'llm_cache_misses': int(cache_stats.get('misses', 0)),
                        'llm_cache_entries': int(cache_stats.get('entries', 0)),
                    },
                )

            content_payloads = self.content_fetcher.fetch_many(contexts)
            reduced_bundles = self.content_reducer.reduce_many(contexts, content_payloads)
            item_analyses = self.item_analyzer.analyze_many(contexts, reduced_bundles)
            sections, raw_response, aggregate_diag = self.aggregate_generator.generate(item_analyses, contexts)
            cache_stats = self._cache_delta(cache_stats_before)

            diagnostics = {
                'mode': snapshot.mode,
                'report_mode': options.mode,
                'selected_items': getattr(selection, 'total_selected', len(contexts)),
                'analyzed_items': len(item_analyses),
                'max_items': options.max_items,
                'section_count': len(sections),
                'content_fetch_count': len(content_payloads),
                'content_reduce_count': len(reduced_bundles),
                'content_async_enabled': bool(content_config.get('ASYNC_ENABLED', False)),
                'content_max_concurrency': int(content_config.get('MAX_CONCURRENCY', 1) or 1),
                'content_request_timeout': int(content_config.get('REQUEST_TIMEOUT', content_config.get('TIMEOUT', 12)) or 12),
                'content_cache_hits': sum(1 for payload in content_payloads if payload.trace.get('cache_hit')),
                'content_fallbacks': sum(1 for payload in content_payloads if payload.status == 'fallback_summary_only'),
                'llm_cache_enabled': bool(cache_stats.get('enabled', False)),
                'llm_cache_hits': int(cache_stats.get('hits', 0)),
                'llm_cache_misses': int(cache_stats.get('misses', 0)),
                'llm_cache_entries': int(cache_stats.get('entries', 0)),
                'error_count': sum(1 for analysis in item_analyses if analysis.diagnostics.get('status') != 'ok'),
                'input_contexts': [asdict(context) for context in contexts],
                'content_payloads': [asdict(payload) for payload in content_payloads],
                'reduced_bundles': [asdict(bundle) for bundle in reduced_bundles],
                'item_analysis_payloads': [asdict(analysis) for analysis in item_analyses],
                'aggregate': aggregate_diag,
            }
            return InsightResult(
                enabled=True,
                strategy='ai',
                sections=sections,
                item_analyses=list(item_analyses),
                raw_response=raw_response,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            cache_stats = self._cache_delta(cache_stats_before)
            return InsightResult(
                enabled=True,
                strategy='ai',
                item_analyses=list(item_analyses),
                raw_response=raw_response,
                diagnostics={
                    'mode': getattr(snapshot, 'mode', ''),
                    'report_mode': options.mode,
                    'selected_items': getattr(selection, 'total_selected', len(contexts)),
                    'analyzed_items': len(item_analyses),
                    'max_items': options.max_items,
                    'llm_cache_enabled': bool(cache_stats.get('enabled', False)),
                    'llm_cache_hits': int(cache_stats.get('hits', 0)),
                    'llm_cache_misses': int(cache_stats.get('misses', 0)),
                    'llm_cache_entries': int(cache_stats.get('entries', 0)),
                    'error': f'{type(exc).__name__}: {exc}',
                    'input_contexts': [asdict(context) for context in contexts],
                    'content_payloads': [asdict(payload) for payload in content_payloads],
                    'reduced_bundles': [asdict(bundle) for bundle in reduced_bundles],
                    'item_analysis_payloads': [asdict(analysis) for analysis in item_analyses],
                },
            )

    def _content_config(self) -> dict[str, Any]:
        content = self.analysis_config.get('CONTENT', {})
        return dict(content) if isinstance(content, Mapping) else {}

    def _item_config(self) -> dict[str, Any]:
        config = self.analysis_config.get('ITEM_ANALYSIS', {})
        return dict(config) if isinstance(config, Mapping) else {}

    def _aggregate_config(self) -> dict[str, Any]:
        config = self.analysis_config.get('AGGREGATE', {})
        return dict(config) if isinstance(config, Mapping) else {}

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
            enabled=bool(cache_config.get('ENABLED', True)),
            ttl_seconds=int(cache_config.get('TTL_SECONDS', 3600) or 3600),
            max_entries=int(cache_config.get('MAX_ENTRIES', 512) or 512),
        )

    def _cache_stats(self) -> dict[str, Any]:
        cache_stats = getattr(self.shared_client, 'cache_stats', None)
        if callable(cache_stats):
            return dict(cache_stats())
        return {'enabled': False, 'entries': 0, 'hits': 0, 'misses': 0}

    def _cache_delta(self, before: Mapping[str, Any]) -> dict[str, Any]:
        after = self._cache_stats()
        return {
            'enabled': after.get('enabled', False),
            'entries': int(after.get('entries', 0) or 0),
            'hits': max(0, int(after.get('hits', 0) or 0) - int(before.get('hits', 0) or 0)),
            'misses': max(0, int(after.get('misses', 0) or 0) - int(before.get('misses', 0) or 0)),
        }
