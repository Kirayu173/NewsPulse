# coding=utf-8
"""Lightweight content enrichment contracts for item summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FetchedContent:
    """Fetched and extracted article text for one selected news item."""

    news_item_id: str
    url: str
    status: str
    title: str = ""
    byline: str = ""
    published_at: str = ""
    excerpt: str = ""
    text: str = ""
    markdown: str = ""
    extraction_method: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReducedSummaryContext:
    """Bounded context passed into the item summary model call."""

    news_item_id: str
    title: str
    source: str
    url: str
    source_summary: str = ""
    extracted_excerpt: str = ""
    key_paragraphs: list[str] = field(default_factory=list)
    evidence_topics: list[str] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)
    rank_signals: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def reduced_text(self) -> str:
        """Return the prompt-facing article context."""

        parts = [self.extracted_excerpt, *self.key_paragraphs]
        return "\n\n".join(part for part in parts if str(part or "").strip())

    @property
    def reduced_char_count(self) -> int:
        return len(self.reduced_text)
