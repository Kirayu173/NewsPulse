# coding=utf-8
"""Aggregate structured item analyses into stable insight sections."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from newspulse.workflow.insight.models import (
    DEFAULT_SECTION_TEMPLATES,
    InsightItemAnalysis,
    InsightNewsContext,
    InsightSectionTemplate,
    build_summary,
)
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response, extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides
from newspulse.workflow.shared.contracts import InsightSection


class InsightAggregateGenerator:
    """Generate stable aggregate insight sections from item-level analyses."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        completion_func: Any | None = None,
        section_templates: tuple[InsightSectionTemplate, ...] = DEFAULT_SECTION_TEMPLATES,
        request_overrides: Mapping[str, Any] | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.section_templates = section_templates
        if client is None:
            if ai_runtime_config is None:
                raise ValueError('AI runtime config is required when no client is provided')
            client = AIRuntimeClient(ai_runtime_config, completion_func=completion_func)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.analysis_config.get('PROMPT_FILE', 'ai_analysis_prompt.txt'),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = build_request_overrides(
            self.analysis_config,
            prompt_template=self.prompt_template,
            operation="insight",
            prompt_name="aggregate",
            overrides=request_overrides,
        )

    def generate(
        self,
        item_analyses: Sequence[InsightItemAnalysis],
        contexts: Sequence[InsightNewsContext],
    ) -> tuple[list[InsightSection], str, dict[str, Any]]:
        valid_analyses = [analysis for analysis in item_analyses if analysis.diagnostics.get('status') == 'ok']
        if not valid_analyses:
            return [], '', {'skipped': True, 'reason': 'no item analyses available'}

        item_payload = _build_item_payload(valid_analyses, contexts)
        source_distribution = _source_distribution(contexts)
        topic_distribution = _topic_distribution(contexts)
        user_prompt = self._render_prompt(item_payload, source_distribution, topic_distribution)
        raw_response = ''
        try:
            raw_response = self.client.chat(
                self.prompt_template.build_messages(user_prompt),
                **self.request_overrides,
            )
            payload = decode_json_response(raw_response)
            sections = _coerce_sections(
                payload,
                item_payload=item_payload,
                section_templates=self.section_templates,
                source_distribution=source_distribution,
                topic_distribution=topic_distribution,
            )
            return sections, raw_response, {
                'item_count': len(valid_analyses),
                'source_distribution': source_distribution,
                'topic_distribution': topic_distribution,
                'section_count': len(sections),
            }
        except Exception as exc:
            fallback = _fallback_section(valid_analyses, source_distribution)
            return fallback, raw_response, {
                'item_count': len(valid_analyses),
                'source_distribution': source_distribution,
                'topic_distribution': topic_distribution,
                'section_count': len(fallback),
                'error': f'{type(exc).__name__}: {exc}',
                'raw_preview': extract_json_block(raw_response)[:500],
            }

    def _render_prompt(
        self,
        item_payload: list[dict[str, Any]],
        source_distribution: dict[str, int],
        topic_distribution: dict[str, int],
    ) -> str:
        user_prompt = self.prompt_template.user_prompt
        replacements = {
            'news_count': str(len(item_payload)),
            'item_analyses_json': json.dumps(item_payload, ensure_ascii=False, indent=2),
            'source_distribution_json': json.dumps(source_distribution, ensure_ascii=False, indent=2),
            'topic_distribution_json': json.dumps(topic_distribution, ensure_ascii=False, indent=2),
            'language': str(self.analysis_config.get('LANGUAGE', 'Chinese') or 'Chinese'),
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace('{' + key + '}', str(value))
        return user_prompt

def _build_item_payload(
    analyses: Sequence[InsightItemAnalysis],
    contexts: Sequence[InsightNewsContext],
) -> list[dict[str, Any]]:
    context_map = {context.news_item_id: context for context in contexts}
    payload = []
    for analysis in analyses:
        context = context_map.get(analysis.news_item_id)
        payload.append(
            {
                'news_item_id': analysis.news_item_id,
                'title': analysis.title,
                'source_name': context.source_name if context is not None else '',
                'source_id': context.source_id if context is not None else '',
                'matched_topics': list(context.selection_evidence.matched_topics) if context is not None else [],
                'what_happened': analysis.what_happened,
                'key_facts': list(analysis.key_facts),
                'why_it_matters': analysis.why_it_matters,
                'watchpoints': list(analysis.watchpoints),
                'uncertainties': list(analysis.uncertainties),
                'evidence': list(analysis.evidence),
                'confidence': analysis.confidence,
            }
        )
    return payload


def _source_distribution(contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter = Counter(context.source_name or context.source_id for context in contexts)
    return dict(counter)


def _topic_distribution(contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for context in contexts:
        counter.update(context.selection_evidence.matched_topics)
    return dict(counter)


def _coerce_sections(
    payload: Any,
    *,
    item_payload: Sequence[dict[str, Any]],
    section_templates: Sequence[InsightSectionTemplate],
    source_distribution: dict[str, int],
    topic_distribution: dict[str, int],
) -> list[InsightSection]:
    if isinstance(payload, Mapping) and isinstance(payload.get('sections'), list):
        sections = []
        for row in payload.get('sections', []):
            if not isinstance(row, Mapping):
                continue
            key = str(row.get('key', '') or '').strip()
            content = str(row.get('content', '') or '').strip()
            if not key or not content:
                continue
            supporting_news_ids = _coerce_id_list(row.get('supporting_news_ids'))
            supporting_topics = _coerce_text_list(row.get('supporting_topics'))
            sections.append(
                InsightSection(
                    key=key,
                    title=str(row.get('title', key) or key).strip(),
                    content=content,
                    summary=str(row.get('summary', '') or build_summary(content)).strip(),
                    metadata={
                        'supporting_news_ids': supporting_news_ids or _default_supporting_news_ids(item_payload),
                        'supporting_topics': supporting_topics,
                        'source_distribution': _coerce_distribution(row.get('source_distribution')) or source_distribution,
                        'section_generator': 'aggregate_llm',
                    },
                )
            )
        if sections:
            return sections

    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError('aggregate insight payload must be a JSON object')

    sections: list[InsightSection] = []
    for template in section_templates:
        raw_value = payload.get(template.field_name)
        content = ''
        supporting_news_ids: list[str] = []
        supporting_topics: list[str] = []
        section_source_distribution: dict[str, int] = source_distribution
        if isinstance(raw_value, Mapping):
            content = str(raw_value.get('content', '') or '').strip()
            supporting_news_ids = _coerce_id_list(raw_value.get('supporting_news_ids'))
            supporting_topics = _coerce_text_list(raw_value.get('supporting_topics'))
            section_source_distribution = _coerce_distribution(raw_value.get('source_distribution')) or source_distribution
        else:
            content = str(raw_value or '').strip()
        if not content:
            continue
        sections.append(
            InsightSection(
                key=template.key,
                title=template.title,
                content=content,
                summary=build_summary(content, template.summary_limit),
                metadata={
                    'supporting_news_ids': supporting_news_ids or _default_supporting_news_ids(item_payload),
                    'supporting_topics': supporting_topics or list(topic_distribution)[:6],
                    'source_distribution': section_source_distribution,
                    'section_generator': 'aggregate_llm',
                },
            )
        )
    if not sections:
        raise AIResponseDecodeError('aggregate insight payload did not contain any section content')
    return sections


def _fallback_section(
    analyses: Sequence[InsightItemAnalysis],
    source_distribution: Mapping[str, int],
) -> list[InsightSection]:
    first = analyses[0]
    content = first.why_it_matters or first.what_happened or '; '.join(first.key_facts[:2])
    if not content:
        content = 'No aggregate insight could be generated.'
    return [
        InsightSection(
            key='core_trends',
            title='Core Trends',
            content=content,
            summary=build_summary(content),
            metadata={
                'supporting_news_ids': [analysis.news_item_id for analysis in analyses[:3]],
                'supporting_topics': [],
                'source_distribution': dict(source_distribution),
                'section_generator': 'aggregate_fallback',
            },
        )
    ]


def _default_supporting_news_ids(item_payload: Sequence[dict[str, Any]]) -> list[str]:
    return [str(row.get('news_item_id', '')).strip() for row in item_payload[:4] if str(row.get('news_item_id', '')).strip()]


def _coerce_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result = []
    for item in value:
        text = str(item or '').strip()
        if text and text not in result:
            result.append(text)
    return result[:8]


def _coerce_text_list(value: Any) -> list[str]:
    return _coerce_id_list(value)


def _coerce_distribution(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        label = str(key or '').strip()
        if not label:
            continue
        try:
            result[label] = int(raw)
        except (TypeError, ValueError):
            continue
    return result
