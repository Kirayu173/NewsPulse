# coding=utf-8
"""Temporary adapter from native insight output back to the legacy analysis shape."""

from __future__ import annotations

from typing import Dict, Optional

from newspulse.ai import AIAnalysisResult
from newspulse.workflow.shared.contracts import InsightResult


def to_ai_analysis_result(
    insight: InsightResult,
    *,
    total_news: int = 0,
    analyzed_news: int = 0,
    max_news_limit: int = 0,
    hotlist_count: int = 0,
    ai_mode: str = "",
) -> Optional[AIAnalysisResult]:
    """Adapt native insight sections to the legacy formatter payload."""

    if not insight.enabled and insight.strategy == "noop":
        return None

    sections = {section.key: section for section in insight.sections}
    standalone_summaries: Dict[str, str] = {}
    for section in insight.sections:
        if not section.key.startswith("standalone:"):
            continue
        platform_name = str(section.metadata.get("platform", "")).strip()
        if not platform_name:
            platform_name = section.key.split(":", 1)[-1]
        if platform_name:
            standalone_summaries[platform_name] = section.content

    diagnostics = dict(insight.diagnostics or {})
    skipped = bool(diagnostics.get("skipped"))
    error = str(diagnostics.get("error") or diagnostics.get("parse_error") or "").strip()

    return AIAnalysisResult(
        core_trends=sections.get("core_trends").content if sections.get("core_trends") else "",
        sentiment_controversy=(
            sections.get("sentiment_controversy").content if sections.get("sentiment_controversy") else ""
        ),
        signals=sections.get("signals").content if sections.get("signals") else "",
        outlook_strategy=sections.get("outlook_strategy").content if sections.get("outlook_strategy") else "",
        standalone_summaries=standalone_summaries,
        raw_response=insight.raw_response,
        success=not skipped and not bool(diagnostics.get("error")) and bool(insight.sections),
        skipped=skipped,
        error=error or str(diagnostics.get("reason", "")).strip(),
        total_news=max(total_news, analyzed_news, hotlist_count),
        analyzed_news=analyzed_news,
        max_news_limit=max_news_limit,
        hotlist_count=hotlist_count or total_news,
        ai_mode=ai_mode,
    )
