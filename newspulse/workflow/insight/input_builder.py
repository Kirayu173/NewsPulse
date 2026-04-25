# coding=utf-8
"""Build useful-only insight inputs from snapshot and selection outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from newspulse.workflow.insight.models import (
    InsightNewsContext,
    InsightRankSignals,
    InsightSelectionEvidence,
    InsightSourceContext,
)
from newspulse.workflow.selection.context_builder import build_selection_context


class InsightInputBuilder:
    """Project stage-4 selection outputs into stage-5 native inputs."""

    def build(
        self,
        snapshot: Any,
        selection: Any,
        *,
        max_items: int = 0,
    ) -> list[InsightNewsContext]:
        del snapshot
        selected_items = list(getattr(selection, 'qualified_items', None) or getattr(selection, 'selected_items', None) or [])
        if max_items > 0:
            selected_items = selected_items[:max_items]

        diagnostics = dict(getattr(selection, 'diagnostics', {}) or {})
        selected_match_map = _map_by_id(diagnostics.get('selected_matches'))
        llm_decision_map = _map_by_id(diagnostics.get('llm_decisions'))
        semantic_candidate_map = _best_semantic_candidates(diagnostics.get('semantic_candidates'))
        group_topic_map = _group_topics_by_item(getattr(selection, 'groups', []) or [])

        contexts: list[InsightNewsContext] = []
        for item in selected_items:
            item_id = str(getattr(item, 'news_item_id', '') or '').strip()
            if not item_id:
                continue
            source_kind = _resolve_source_kind(item)
            selection_context = build_selection_context(item)
            selected_match = selected_match_map.get(item_id, {})
            semantic_candidate = semantic_candidate_map.get(item_id, {})
            llm_decision = llm_decision_map.get(item_id, {})
            matched_topics = _collect_topics(selected_match, llm_decision)
            if not matched_topics:
                matched_topics = list(group_topic_map.get(item_id, []))
            contexts.append(
                InsightNewsContext(
                    news_item_id=item_id,
                    title=str(getattr(item, 'title', '') or '').strip(),
                    source_id=str(getattr(item, 'source_id', '') or '').strip(),
                    source_name=str(getattr(item, 'source_name', '') or getattr(item, 'source_id', '') or '').strip(),
                    url=str(getattr(item, 'url', '') or '').strip(),
                    mobile_url=str(getattr(item, 'mobile_url', '') or '').strip(),
                    rank_signals=_build_rank_signals(item),
                    source_context=InsightSourceContext(
                        source_kind=source_kind,
                        summary=selection_context.summary,
                        attributes=tuple(_build_source_attributes(item, selection_context, source_kind)),
                        metadata=_whitelist_source_metadata(item, source_kind),
                    ),
                    selection_evidence=InsightSelectionEvidence(
                        matched_topics=tuple(matched_topics),
                        semantic_score=float(semantic_candidate.get('score', 0.0) or 0.0),
                        quality_score=float(
                            selected_match.get('quality_score', llm_decision.get('quality_score', 0.0)) or 0.0
                        ),
                        decision_layer=str(selected_match.get('decision_layer', '') or '').strip(),
                        llm_reasons=tuple(_collect_reasons(selected_match, llm_decision)),
                    ),
                )
            )
        return contexts


def _build_rank_signals(item: Any) -> InsightRankSignals:
    raw_ranks = [int(rank) for rank in list(getattr(item, 'ranks', []) or []) if str(rank).strip()]
    current_rank = int(getattr(item, 'current_rank', 0) or 0)
    if current_rank > 0 and current_rank not in raw_ranks:
        raw_ranks.append(current_rank)
    normalized = sorted(rank for rank in raw_ranks if rank > 0)
    best_rank = normalized[0] if normalized else current_rank
    worst_rank = normalized[-1] if normalized else current_rank
    return InsightRankSignals(
        current_rank=current_rank,
        best_rank=best_rank,
        worst_rank=worst_rank,
        appearance_count=max(1, int(getattr(item, 'count', 1) or 1)),
        rank_trend=_resolve_rank_trend(raw_ranks or [current_rank]),
    )


def _resolve_rank_trend(ranks: Sequence[int]) -> str:
    valid = [int(rank) for rank in ranks if int(rank) > 0]
    if len(valid) < 2:
        return 'stable' if valid else ''
    first = valid[0]
    last = valid[-1]
    if last < first:
        return 'up'
    if last > first:
        return 'down'
    return 'stable'


def _resolve_source_kind(item: Any) -> str:
    metadata = getattr(item, 'metadata', {}) or {}
    if isinstance(metadata, Mapping):
        source_kind = str(metadata.get('source_kind', '') or '').strip()
        if source_kind:
            return source_kind
    source_id = str(getattr(item, 'source_id', '') or '').strip()
    if source_id == 'hackernews':
        return 'hackernews_item'
    return 'article'


def _build_source_attributes(item: Any, selection_context: Any, source_kind: str) -> list[str]:
    attributes = list(getattr(selection_context, 'attributes', ()) or ())
    host = _resolve_host(str(getattr(item, 'url', '') or getattr(item, 'mobile_url', '') or ''))
    if host and all(not line.startswith('host: ') for line in attributes):
        attributes.append(f'host: {host}')
    return [line for line in attributes if str(line).strip()]


def _whitelist_source_metadata(item: Any, source_kind: str) -> dict[str, Any]:
    metadata = getattr(item, 'metadata', {}) or {}
    if not isinstance(metadata, Mapping):
        return {}

    if source_kind == 'github_repository':
        github = metadata.get('github')
        if not isinstance(github, Mapping):
            return {}
        clean: dict[str, Any] = {}
        for key in (
            'full_name',
            'owner',
            'repo',
            'description',
            'language',
            'topics',
            'stars_total',
            'stars_today',
            'forks_total',
            'created_at',
            'pushed_at',
            'archived',
            'fork',
            'source_variant',
            'enriched_by',
        ):
            value = github.get(key)
            if value in (None, '', [], {}):
                continue
            clean[key] = list(value) if isinstance(value, tuple) else value
        return clean

    clean = {}
    for key in ('author', 'published_at', 'channel', 'category', 'tags'):
        value = metadata.get(key)
        if value in (None, '', [], {}):
            continue
        clean[key] = list(value) if isinstance(value, tuple) else value
    return clean


def _collect_topics(*rows: Mapping[str, Any]) -> list[str]:
    topics: list[str] = []
    for row in rows:
        value = row.get('matched_topics') if isinstance(row, Mapping) else None
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, Sequence):
            continue
        for topic in value:
            text = str(topic or '').strip()
            if text and text not in topics:
                topics.append(text)
    return topics


def _group_topics_by_item(groups: Any) -> dict[str, tuple[str, ...]]:
    mapped: dict[str, list[str]] = {}
    if not isinstance(groups, Sequence):
        return {}
    for group in groups:
        label = str(getattr(group, 'label', '') or getattr(group, 'key', '') or '').strip()
        if not label:
            continue
        for item in list(getattr(group, 'items', []) or []):
            item_id = str(getattr(item, 'news_item_id', '') or '').strip()
            if not item_id:
                continue
            topics = mapped.setdefault(item_id, [])
            if label not in topics:
                topics.append(label)
    return {item_id: tuple(topics) for item_id, topics in mapped.items()}


def _collect_reasons(*rows: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for row in rows:
        value = row.get('reasons') if isinstance(row, Mapping) else None
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, Sequence):
            continue
        for reason in value:
            text = str(reason or '').strip()
            if text and text not in reasons:
                reasons.append(text)
    return reasons


def _map_by_id(rows: Any) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, Sequence):
        return mapped
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item_id = str(row.get('news_item_id', '') or '').strip()
        if item_id:
            mapped[item_id] = dict(row)
    return mapped


def _best_semantic_candidates(rows: Any) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, Sequence):
        return best
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item_id = str(row.get('news_item_id', '') or '').strip()
        if not item_id:
            continue
        current = best.get(item_id)
        score = float(row.get('score', 0.0) or 0.0)
        if current is None or score > float(current.get('score', 0.0) or 0.0):
            best[item_id] = dict(row)
    return best


def _resolve_host(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    return str(parsed.netloc or '').strip().lower()
