# coding=utf-8
"""Native contracts and helpers used by the insight stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InsightRankSignals:
    """Compressed rank signals passed into the insight stage."""

    current_rank: int = 0
    best_rank: int = 0
    worst_rank: int = 0
    appearance_count: int = 1
    rank_trend: str = ""


@dataclass(frozen=True)
class InsightSelectionEvidence:
    """Useful-only evidence distilled from the selection funnel."""

    matched_topics: tuple[str, ...] = ()
    semantic_score: float = 0.0
    quality_score: float = 0.0
    decision_layer: str = ""
    llm_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsightSourceContext:
    """Source-aware context kept after metadata white-listing."""

    source_kind: str = ""
    summary: str = ""
    attributes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InsightNewsContext:
    """One selected news item normalized for the insight workflow."""

    news_item_id: str
    title: str
    source_id: str
    source_name: str
    url: str = ""
    mobile_url: str = ""
    rank_signals: InsightRankSignals = field(default_factory=InsightRankSignals)
    source_context: InsightSourceContext = field(default_factory=InsightSourceContext)
    selection_evidence: InsightSelectionEvidence = field(default_factory=InsightSelectionEvidence)


@dataclass(frozen=True)
class InsightContentPayload:
    """Fetched or synthesized content payload for one selected news item."""

    news_item_id: str
    status: str
    source_type: str
    normalized_url: str = ""
    final_url: str = ""
    title: str = ""
    excerpt: str = ""
    content_text: str = ""
    content_markdown: str = ""
    published_at: str = ""
    author: str = ""
    extractor_name: str = ""
    content_hash: str = ""
    error_type: str = ""
    error_message: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReducedContentBundle:
    """Reduced high-signal content that is safe to send to the model."""

    news_item_id: str
    status: str
    anchor_text: str = ""
    reduced_text: str = ""
    selected_sentences: tuple[str, ...] = ()
    evidence_sentences: tuple[str, ...] = ()
    reducer_name: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InsightItemAnalysis:
    """Structured per-item analysis produced before aggregate insight generation."""

    news_item_id: str
    title: str
    what_happened: str = ""
    key_facts: tuple[str, ...] = ()
    why_it_matters: str = ""
    watchpoints: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedContent:
    """Normalized extractor output before it is saved into storage."""

    success: bool
    title: str = ""
    excerpt: str = ""
    text: str = ""
    markdown: str = ""
    final_url: str = ""
    published_at: str = ""
    author: str = ""
    extractor_name: str = ""
    trace: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class InsightSectionTemplate:
    """Definition used to normalize aggregate JSON fields into insight sections."""

    key: str
    title: str
    field_name: str
    summary_limit: int = 120


DEFAULT_SECTION_TEMPLATES = (
    InsightSectionTemplate(key="core_trends", title="Core Trends", field_name="core_trends"),
    InsightSectionTemplate(
        key="sentiment_controversy",
        title="Sentiment & Controversy",
        field_name="sentiment_controversy",
    ),
    InsightSectionTemplate(key="signals", title="Signals", field_name="signals"),
    InsightSectionTemplate(
        key="outlook_strategy",
        title="Outlook & Strategy",
        field_name="outlook_strategy",
    ),
)


def build_summary(content: str, limit: int = 120) -> str:
    """Create a short plain-text summary from a longer paragraph."""

    normalized = " ".join((content or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."
