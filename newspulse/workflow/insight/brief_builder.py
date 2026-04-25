# coding=utf-8
"""Build compact stage-5 insight briefs from normalized news contexts."""

from __future__ import annotations

from collections.abc import Sequence

from newspulse.workflow.insight.models import InsightBrief, InsightNewsContext


class InsightBriefBuilder:
    """Convert selection-derived contexts into lightweight aggregate inputs."""

    def build_many(self, contexts: Sequence[InsightNewsContext]) -> list[InsightBrief]:
        briefs: list[InsightBrief] = []
        for context in contexts:
            brief = self.build_one(context)
            if brief is not None:
                briefs.append(brief)
        return briefs

    def build_one(self, context: InsightNewsContext) -> InsightBrief | None:
        news_item_id = str(context.news_item_id or "").strip()
        title = str(context.title or "").strip()
        if not news_item_id or not title:
            return None

        source_context = context.source_context
        evidence = context.selection_evidence
        rank_signals = context.rank_signals

        return InsightBrief(
            news_item_id=news_item_id,
            title=title,
            source_id=str(context.source_id or "").strip(),
            source_name=str(context.source_name or context.source_id or "").strip(),
            source_kind=str(source_context.source_kind or "").strip(),
            summary=_build_summary(context),
            attributes=tuple(_compact_values(source_context.attributes, limit=6, drop_prefixes=("route:",))),
            matched_topics=tuple(_compact_values(evidence.matched_topics, limit=6)),
            llm_reasons=tuple(_compact_values(evidence.llm_reasons, limit=4)),
            semantic_score=float(evidence.semantic_score or 0.0),
            quality_score=float(evidence.quality_score or 0.0),
            current_rank=int(rank_signals.current_rank or 0),
            rank_trend=str(rank_signals.rank_trend or "").strip(),
            url=str(context.url or context.mobile_url or "").strip(),
        )


def _build_summary(context: InsightNewsContext) -> str:
    source_context = context.source_context
    evidence = context.selection_evidence

    summary = _normalize_text(source_context.summary, limit=220)
    if summary:
        return summary

    parts: list[str] = []
    topics = _compact_values(evidence.matched_topics, limit=3)
    reasons = _compact_values(evidence.llm_reasons, limit=2)

    if topics:
        parts.append("主题: " + " / ".join(topics))
    if reasons:
        parts.append("入选原因: " + "；".join(reasons))
    if context.source_name:
        parts.append("来源: " + str(context.source_name).strip())

    synthesized = " | ".join(part for part in parts if part)
    if synthesized:
        return _normalize_text(synthesized, limit=220)
    return _normalize_text(context.title, limit=220)


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


def _normalize_text(value: object, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
