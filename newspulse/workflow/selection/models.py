# coding=utf-8
"""Private models used by the selection stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from re import Pattern
from typing import Any

from newspulse.workflow.shared.contracts import HotlistItem, SelectionRejectedItem


@dataclass(frozen=True)
class KeywordToken:
    """Single keyword token used by the runtime matcher."""

    text: str
    is_regex: bool = False
    pattern: Pattern[str] | None = None
    display_name: str = ""

    @property
    def label(self) -> str:
        return self.display_name or self.text


@dataclass(frozen=True)
class KeywordRuleGroup:
    """One keyword-selection group used by the runtime strategy."""

    group_key: str
    label: str
    position: int
    max_items: int = 0
    required_tokens: tuple[KeywordToken, ...] = ()
    normal_tokens: tuple[KeywordToken, ...] = ()


@dataclass(frozen=True)
class KeywordRuleSet:
    """Typed keyword rule set loaded from the frequency config file."""

    groups: tuple[KeywordRuleGroup, ...] = ()
    filter_tokens: tuple[KeywordToken, ...] = ()
    global_filters: tuple[str, ...] = ()
    source_path: str = ""


@dataclass
class KeywordGroupBucket:
    """Accumulated matched items for a keyword selection group."""

    definition: KeywordRuleGroup
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
    summary: str = ""
    context_lines: tuple[str, ...] = ()
    rendered_context: str = ""
    persisted_news_id: int | None = None


@dataclass(frozen=True)
class AIClassificationResult:
    """Normalized AI classification output for one selected news item."""

    news_item_id: str
    tag_id: int
    relevance_score: float
    source_type: str = "hotlist"
    persisted_news_id: int | None = None


@dataclass(frozen=True)
class AIQualityDecision:
    """Final LLM keep/drop decision for one candidate item."""

    news_item_id: str
    keep: bool
    quality_score: float = 0.0
    reasons: tuple[str, ...] = ()
    evidence: str = ""
    matched_topics: tuple[str, ...] = ()
    persisted_news_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionTopic:
    """Typed topic definition shared by semantic and AI selection layers."""

    topic_id: int
    label: str
    description: str = ""
    priority: int = 9999
    seed_keywords: tuple[str, ...] = ()
    negative_keywords: tuple[str, ...] = ()
    source: str = "ai_tag"

    def to_query_text(self) -> str:
        """Serialize the topic into a compact semantic-recall query string."""

        parts = [self.label.strip()]
        if self.description.strip():
            parts.append(self.description.strip())
        if self.seed_keywords:
            parts.append(" ".join(keyword for keyword in self.seed_keywords if keyword))
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class SelectionCandidate:
    """One topic candidate emitted by an intermediate selection layer."""

    news_item: HotlistItem
    topic_id: int
    topic_label: str
    score: float
    source_layers: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionDecision:
    """Finalized intermediate decision before projecting a SelectionResult."""

    news_item_id: str
    final_topic_id: int
    final_topic_label: str
    decision_layer: str
    decision_reason: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticSelectionResult:
    """Structured semantic-recall output used by the Phase-A pipeline."""

    topics: tuple[SelectionTopic, ...] = ()
    candidates: tuple[SelectionCandidate, ...] = ()
    decisions: tuple[SelectionDecision, ...] = ()
    passed_items: tuple[HotlistItem, ...] = ()
    rejected_items: tuple[SelectionRejectedItem, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
