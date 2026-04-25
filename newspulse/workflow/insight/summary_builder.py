# coding=utf-8
"""Build topic-first structured summaries from normalized news contexts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from newspulse.workflow.insight.models import InsightNewsContext
from newspulse.workflow.shared.contracts import InsightSummary, InsightSummaryBundle


@dataclass
class _ThemeCluster:
    key: str
    title: str
    contexts: list[InsightNewsContext] = field(default_factory=list)
    evidence_topics: list[str] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)


class InsightSummaryBuilder:
    """Create item, theme and report summaries without extra model calls."""

    def build_many(self, contexts: Sequence[InsightNewsContext]) -> InsightSummaryBundle:
        valid_contexts = [
            context
            for context in contexts
            if str(context.news_item_id or "").strip() and str(context.title or "").strip()
        ]
        item_summaries = [self.build_item_summary(context) for context in valid_contexts]
        theme_summaries = self._build_theme_summaries(valid_contexts)
        report_summary = self._build_report_summary(valid_contexts, theme_summaries)
        return InsightSummaryBundle(
            item_summaries=item_summaries,
            theme_summaries=theme_summaries,
            report_summary=report_summary,
        )

    def build_item_summary(self, context: InsightNewsContext) -> InsightSummary:
        source_context = context.source_context
        evidence = context.selection_evidence
        rank_signals = context.rank_signals
        item_id = str(context.news_item_id or "").strip()
        source_name = str(context.source_name or context.source_id or "").strip()
        topics = _compact_values(evidence.matched_topics, limit=6)
        reasons = _compact_values(evidence.llm_reasons, limit=4)
        theme_key = _theme_key(topics[0]) if topics else ""
        theme_title = topics[0] if topics else ""

        return InsightSummary(
            kind="item",
            key=f"item:{item_id}",
            title=str(context.title or "").strip(),
            summary=_build_item_summary_text(context),
            item_ids=[item_id],
            theme_keys=[theme_key] if theme_key else [],
            evidence_topics=topics,
            evidence_notes=reasons,
            sources=[source_name] if source_name else [],
            expanded=True,
            metadata={
                "news_item_id": item_id,
                "source_id": str(context.source_id or "").strip(),
                "source_name": source_name,
                "source_kind": str(source_context.source_kind or "").strip(),
                "attributes": _compact_values(source_context.attributes, limit=6, drop_prefixes=("route:",)),
                "semantic_score": float(evidence.semantic_score or 0.0),
                "quality_score": float(evidence.quality_score or 0.0),
                "current_rank": int(rank_signals.current_rank or 0),
                "rank_trend": str(rank_signals.rank_trend or "").strip(),
                "url": str(context.url or context.mobile_url or "").strip(),
                "theme_title": theme_title,
                "summary_scope": "item",
                "expanded_by_default": True,
            },
        )

    def _build_theme_summaries(self, contexts: Sequence[InsightNewsContext]) -> list[InsightSummary]:
        clusters = self._cluster_by_theme(contexts)
        ordered = sorted(
            clusters.values(),
            key=lambda cluster: _theme_sort_key(cluster),
        )
        summaries: list[InsightSummary] = []
        for cluster in ordered:
            ordered_contexts = sorted(cluster.contexts, key=_context_sort_key)
            item_ids = [str(context.news_item_id or "").strip() for context in ordered_contexts]
            representative = item_ids[:3]
            supporting = item_ids[3:]
            sources = _dedupe(
                str(context.source_name or context.source_id or "").strip()
                for context in ordered_contexts
            )
            representative_titles = [
                str(context.title or "").strip()
                for context in ordered_contexts[:3]
                if str(context.title or "").strip()
            ]
            summaries.append(
                InsightSummary(
                    kind="theme",
                    key=cluster.key,
                    title=cluster.title,
                    summary=_build_theme_summary_text(cluster.title, representative_titles, len(ordered_contexts)),
                    item_ids=item_ids,
                    theme_keys=[cluster.key],
                    evidence_topics=cluster.evidence_topics,
                    evidence_notes=cluster.evidence_notes,
                    sources=sources,
                    expanded=True,
                    metadata={
                        "representative_item_ids": representative,
                        "supporting_item_ids": supporting,
                        "representative_titles": representative_titles,
                        "source_evidence": sources,
                        "item_count": len(item_ids),
                        "llm_reason_count": _llm_reason_count(ordered_contexts),
                        "average_quality_score": _average_quality_score(ordered_contexts),
                        "summary_scope": "theme",
                        "expanded_by_default": True,
                    },
                )
            )
        return summaries

    def _cluster_by_theme(self, contexts: Sequence[InsightNewsContext]) -> dict[str, _ThemeCluster]:
        clusters: dict[str, _ThemeCluster] = {}
        for context in contexts:
            topics = _compact_values(context.selection_evidence.matched_topics, limit=6)
            if not topics:
                continue
            primary_topic = topics[0]
            key = _theme_key(primary_topic)
            cluster = clusters.setdefault(
                key,
                _ThemeCluster(key=key, title=primary_topic),
            )
            cluster.contexts.append(context)
            cluster.evidence_topics = _merge_limited(cluster.evidence_topics, topics, limit=8)
            cluster.evidence_notes = _merge_limited(
                cluster.evidence_notes,
                _compact_values(context.selection_evidence.llm_reasons, limit=4),
                limit=10,
            )
        return clusters

    def _build_report_summary(
        self,
        contexts: Sequence[InsightNewsContext],
        theme_summaries: Sequence[InsightSummary],
    ) -> InsightSummary | None:
        if not contexts:
            return None

        item_ids = [str(context.news_item_id or "").strip() for context in contexts]
        theme_titles = [summary.title for summary in theme_summaries if summary.title]
        topic_counts: Counter[str] = Counter()
        for context in contexts:
            topic_counts.update(_compact_values(context.selection_evidence.matched_topics, limit=6))
        evidence_topics = [topic for topic, _ in topic_counts.most_common(8)]
        sources = _dedupe(str(context.source_name or context.source_id or "").strip() for context in contexts)

        return InsightSummary(
            kind="report",
            key="report",
            title="报告摘要",
            summary=_build_report_summary_text(len(contexts), theme_titles),
            item_ids=item_ids,
            theme_keys=[summary.key for summary in theme_summaries],
            evidence_topics=evidence_topics,
            evidence_notes=_dedupe(
                note
                for context in contexts
                for note in _compact_values(context.selection_evidence.llm_reasons, limit=3)
            )[:12],
            sources=sources,
            expanded=True,
            metadata={
                "item_count": len(contexts),
                "theme_count": len(theme_summaries),
                "source_evidence": sources,
                "topic_distribution": dict(topic_counts),
                "summary_scope": "report",
                "expanded_by_default": True,
            },
        )


def _build_item_summary_text(context: InsightNewsContext) -> str:
    source_context = context.source_context
    evidence = context.selection_evidence

    source_summary = _normalize_text(source_context.summary, limit=220)
    if source_summary:
        return source_summary

    topics = _compact_values(evidence.matched_topics, limit=3)
    reasons = _compact_values(evidence.llm_reasons, limit=2)
    parts: list[str] = []
    if topics:
        parts.append("主题: " + " / ".join(topics))
    if reasons:
        parts.append("入选原因: " + "；".join(reasons))
    synthesized = " | ".join(parts)
    if synthesized:
        return _normalize_text(synthesized, limit=220)
    return _normalize_text(context.title, limit=220)


def _build_theme_summary_text(theme_title: str, representative_titles: Sequence[str], item_count: int) -> str:
    if representative_titles:
        return f"{theme_title} 覆盖 {item_count} 条入选新闻，代表信号包括：" + "；".join(representative_titles[:3])
    return f"{theme_title} 覆盖 {item_count} 条入选新闻。"


def _build_report_summary_text(item_count: int, theme_titles: Sequence[str]) -> str:
    if theme_titles:
        return f"{item_count} 条入选新闻形成 {len(theme_titles)} 个主题：" + "、".join(theme_titles[:5])
    return f"{item_count} 条入选新闻暂无稳定主题聚合，仅保留单条摘要。"


def _theme_sort_key(cluster: _ThemeCluster) -> tuple[float, int, float, int, str]:
    contexts = cluster.contexts
    return (
        -float(_llm_reason_count(contexts)),
        -len(contexts),
        -_average_quality_score(contexts),
        min((int(context.rank_signals.current_rank or 9999) for context in contexts), default=9999),
        cluster.title.lower(),
    )


def _context_sort_key(context: InsightNewsContext) -> tuple[float, float, int, str]:
    evidence = context.selection_evidence
    rank = int(context.rank_signals.current_rank or 9999)
    return (
        -float(evidence.quality_score or 0.0),
        -float(evidence.semantic_score or 0.0),
        rank,
        str(context.title or "").lower(),
    )


def _llm_reason_count(contexts: Sequence[InsightNewsContext]) -> int:
    return sum(len(_compact_values(context.selection_evidence.llm_reasons, limit=8)) for context in contexts)


def _average_quality_score(contexts: Sequence[InsightNewsContext]) -> float:
    if not contexts:
        return 0.0
    return sum(float(context.selection_evidence.quality_score or 0.0) for context in contexts) / len(contexts)


def _theme_key(topic: str) -> str:
    normalized = _normalize_text(topic, limit=80).lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in normalized)
    safe = "-".join(part for part in safe.split("-") if part)
    return f"theme:{safe or 'untitled'}"


def _compact_values(
    values: Sequence[str] | tuple[str, ...],
    *,
    limit: int,
    drop_prefixes: tuple[str, ...] = (),
) -> list[str]:
    normalized: list[str] = []
    for raw in values or ():
        text = _normalize_text(raw, limit=96)
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in drop_prefixes):
            continue
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _merge_limited(existing: Sequence[str], new_values: Sequence[str], *, limit: int) -> list[str]:
    return _dedupe([*existing, *new_values])[:limit]


def _dedupe(values: Sequence[str] | object) -> list[str]:
    normalized: list[str] = []
    for raw in values or ():
        text = _normalize_text(raw, limit=120)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_text(value: object, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
