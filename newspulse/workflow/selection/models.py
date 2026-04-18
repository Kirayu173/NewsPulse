# coding=utf-8
"""Private models used by the selection stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from newspulse.workflow.shared.contracts import HotlistItem


@dataclass(frozen=True)
class KeywordGroupDefinition:
    """Keyword group definition loaded from the frequency words config."""

    group_key: str
    label: str
    position: int
    max_items: int = 0
    required: list[dict[str, Any]] = field(default_factory=list)
    normal: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class KeywordGroupBucket:
    """Accumulated matched items for a keyword selection group."""

    definition: KeywordGroupDefinition
    matched_items: list[HotlistItem] = field(default_factory=list)

    @property
    def total_matched(self) -> int:
        """Return the total matched item count before output capping."""

        return len(self.matched_items)


@dataclass(frozen=True)
class AIActiveTag:
    """Active AI tag row loaded from the compatibility storage tables."""

    id: int
    tag: str
    description: str = ""
    priority: int = 9999
    version: int = 0
    prompt_hash: str = ""


@dataclass(frozen=True)
class AIBatchNewsItem:
    """Single snapshot item prepared for an AI classification batch."""

    prompt_id: int
    news_item_id: str
    title: str
    source_id: str = ""
    source_name: str = ""
    persisted_news_id: int | None = None


@dataclass(frozen=True)
class AIClassificationResult:
    """Normalized AI classification output for one selected news item."""

    news_item_id: str
    tag_id: int
    relevance_score: float
    source_type: str = "hotlist"
    persisted_news_id: int | None = None
