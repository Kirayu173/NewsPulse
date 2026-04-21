# coding=utf-8
"""Per-item structured insight analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from newspulse.workflow.insight.models import InsightItemAnalysis, InsightNewsContext, ReducedContentBundle
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template


class InsightItemAnalyzer:
    """Generate a structured JSON analysis for every selected news item."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        completion_func: Any | None = None,
        request_overrides: Mapping[str, Any] | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        if client is None:
            if ai_runtime_config is None:
                raise ValueError('AI runtime config is required when no client is provided')
            client = AIRuntimeClient(ai_runtime_config, completion_func=completion_func)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.analysis_config.get('ITEM_PROMPT_FILE', 'ai_insight_item_prompt.txt'),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = self._build_request_overrides(request_overrides)

    def analyze_many(
        self,
        contexts: Sequence[InsightNewsContext],
        reduced_bundles: Sequence[ReducedContentBundle],
    ) -> list[InsightItemAnalysis]:
        bundle_map = {bundle.news_item_id: bundle for bundle in reduced_bundles}
        return [self.analyze_one(context, bundle_map.get(context.news_item_id)) for context in contexts]

    def analyze_one(
        self,
        context: InsightNewsContext,
        bundle: ReducedContentBundle | None,
    ) -> InsightItemAnalysis:
        bundle = bundle or ReducedContentBundle(
            news_item_id=context.news_item_id,
            status='missing_bundle',
            anchor_text=context.title,
            reduced_text=context.source_context.summary or context.title,
        )
        user_prompt = self._render_prompt(context, bundle)
        raw_response = ''
        try:
            raw_response = self.client.chat(
                self.prompt_template.build_messages(user_prompt),
                **self.request_overrides,
            )
            payload = decode_json_response(raw_response)
            return _coerce_analysis(payload, context, bundle, raw_response=raw_response)
        except Exception as exc:
            return InsightItemAnalysis(
                news_item_id=context.news_item_id,
                title=context.title,
                evidence=tuple(bundle.evidence_sentences[:2]),
                diagnostics={
                    'status': 'error',
                    'error': f'{type(exc).__name__}: {exc}',
                    'raw_preview': raw_response[:500],
                    'bundle_status': bundle.status,
                    'reduced_chars': len(bundle.reduced_text or ''),
                },
            )

    def _render_prompt(self, context: InsightNewsContext, bundle: ReducedContentBundle) -> str:
        user_prompt = self.prompt_template.user_prompt
        replacements = {
            'title': context.title,
            'source_name': context.source_name or context.source_id,
            'source_id': context.source_id,
            'rank_signals': _render_rank_signals(context),
            'source_summary': context.source_context.summary,
            'source_attributes': '\n'.join(f'- {line}' for line in context.source_context.attributes if str(line).strip()) or '-',
            'matched_topics': ', '.join(context.selection_evidence.matched_topics) or '-',
            'selection_reasons': '; '.join(context.selection_evidence.llm_reasons) or '-',
            'quality_score': f'{context.selection_evidence.quality_score:.3f}',
            'semantic_score': f'{context.selection_evidence.semantic_score:.3f}',
            'reduced_content': bundle.reduced_text or context.source_context.summary or context.title,
            'evidence_sentences': '\n'.join(f'- {line}' for line in bundle.evidence_sentences if str(line).strip()) or '-',
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace('{' + key + '}', str(value))
        return user_prompt

    def _build_request_overrides(self, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        request_overrides = dict(overrides or {})
        timeout = self.analysis_config.get('TIMEOUT')
        if timeout is not None and 'timeout' not in request_overrides:
            request_overrides['timeout'] = int(timeout)
        num_retries = self.analysis_config.get('NUM_RETRIES')
        if num_retries is not None and 'num_retries' not in request_overrides:
            request_overrides['num_retries'] = int(num_retries)
        extra_params = self.analysis_config.get('EXTRA_PARAMS', {})
        if isinstance(extra_params, Mapping):
            for key, value in extra_params.items():
                request_overrides.setdefault(key, value)
        return request_overrides


def _coerce_analysis(
    payload: Any,
    context: InsightNewsContext,
    bundle: ReducedContentBundle,
    *,
    raw_response: str,
) -> InsightItemAnalysis:
    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError('item analysis payload must be a JSON object')

    key_facts = _coerce_list(payload.get('key_facts'))
    watchpoints = _coerce_list(payload.get('watchpoints'))
    uncertainties = _coerce_list(payload.get('uncertainties'))
    evidence = _coerce_list(payload.get('evidence')) or list(bundle.evidence_sentences[:2])
    confidence = _coerce_confidence(payload.get('confidence'))

    return InsightItemAnalysis(
        news_item_id=context.news_item_id,
        title=context.title,
        what_happened=str(payload.get('what_happened', '') or '').strip(),
        key_facts=tuple(key_facts),
        why_it_matters=str(payload.get('why_it_matters', '') or '').strip(),
        watchpoints=tuple(watchpoints),
        uncertainties=tuple(uncertainties),
        evidence=tuple(evidence),
        confidence=confidence,
        diagnostics={
            'status': 'ok',
            'bundle_status': bundle.status,
            'reduced_chars': len(bundle.reduced_text or ''),
            'raw_preview': raw_response[:500],
        },
    )


def _render_rank_signals(context: InsightNewsContext) -> str:
    signals = context.rank_signals
    parts = []
    if signals.current_rank > 0:
        parts.append(f'current_rank={signals.current_rank}')
    if signals.best_rank > 0:
        parts.append(f'best_rank={signals.best_rank}')
    if signals.worst_rank > 0:
        parts.append(f'worst_rank={signals.worst_rank}')
    parts.append(f'appearance_count={signals.appearance_count}')
    if signals.rank_trend:
        parts.append(f'rank_trend={signals.rank_trend}')
    return '; '.join(parts) or '-'


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or '').strip()
        if text and text not in result:
            result.append(text)
    return result[:6]


def _coerce_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number
