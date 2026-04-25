# coding=utf-8
"""Native context contracts and helpers used by the insight stage."""

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
class InsightSectionTemplate:
    """Definition used to normalize aggregate JSON fields into insight sections."""

    key: str
    title: str
    field_name: str
    summary_limit: int = 120


SECTION_TITLE_BY_KEY = {
    "core_trends": "核心趋势",
    "sentiment_controversy": "争议与分歧",
    "signals": "关键信号",
    "outlook_strategy": "后续观察",
}


DEFAULT_SECTION_TEMPLATES = (
    InsightSectionTemplate(
        key="core_trends",
        title=SECTION_TITLE_BY_KEY["core_trends"],
        field_name="core_trends",
    ),
    InsightSectionTemplate(
        key="sentiment_controversy",
        title=SECTION_TITLE_BY_KEY["sentiment_controversy"],
        field_name="sentiment_controversy",
    ),
    InsightSectionTemplate(
        key="signals",
        title=SECTION_TITLE_BY_KEY["signals"],
        field_name="signals",
    ),
    InsightSectionTemplate(
        key="outlook_strategy",
        title=SECTION_TITLE_BY_KEY["outlook_strategy"],
        field_name="outlook_strategy",
    ),
)


def resolve_section_title(key: str, fallback: str = "") -> str:
    """Return the stable rendered title for a known section key."""

    normalized_key = str(key or "").strip()
    return SECTION_TITLE_BY_KEY.get(normalized_key, str(fallback or normalized_key).strip())


def build_summary(content: str, limit: int = 120) -> str:
    """Create a short plain-text summary from a longer paragraph."""

    normalized = " ".join((content or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."
