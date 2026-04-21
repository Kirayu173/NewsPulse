# coding=utf-8
"""Cross-stage data contracts for the native workflow pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class HotlistItem:
    """Normalized hotlist item shared across the workflow stages."""

    news_item_id: str
    source_id: str
    title: str
    source_name: str = ""
    url: str = ""
    mobile_url: str = ""
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    current_rank: int = 0
    ranks: List[int] = field(default_factory=list)
    first_time: str = ""
    last_time: str = ""
    count: int = 1
    rank_timeline: List[Dict[str, Any]] = field(default_factory=list)
    is_new: bool = False


@dataclass
class SourceFailure:
    """Failure details kept in the snapshot for downstream reporting."""

    source_id: str
    source_name: str = ""
    reason: str = ""
    resolved_source_id: str = ""
    exception_type: str = ""
    message: str = ""
    attempts: int = 1


@dataclass
class StandaloneSection:
    """Standalone hotlist section carried through the report pipeline."""

    key: str
    label: str
    items: List[HotlistItem] = field(default_factory=list)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionGroup:
    """Unified group output for keyword and AI-based selection."""

    key: str
    label: str
    items: List[HotlistItem] = field(default_factory=list)
    description: str = ""
    position: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionRejectedItem:
    """One item rejected by a gate in the selection funnel."""

    news_item_id: str
    source_id: str = ""
    source_name: str = ""
    title: str = ""
    rejected_stage: str = ""
    rejected_reason: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InsightSection:
    """Structured insight block produced by the insight stage."""

    key: str
    title: str
    content: str
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotlistSnapshot:
    """Unique downstream input generated from stored hotlist data."""

    mode: str
    generated_at: str
    items: List[HotlistItem] = field(default_factory=list)
    failed_sources: List[SourceFailure] = field(default_factory=list)
    new_items: List[HotlistItem] = field(default_factory=list)
    standalone_sections: List[StandaloneSection] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def item_count(self) -> int:
        """Return the number of normalized items in the snapshot."""

        return len(self.items)


@dataclass
class SelectionResult:
    """Selection stage output used by insight, render and delivery stages."""

    strategy: str
    qualified_items: List[HotlistItem] = field(default_factory=list)
    rejected_items: List[SelectionRejectedItem] = field(default_factory=list)
    groups: List[SelectionGroup] = field(default_factory=list)
    selected_items: List[HotlistItem] = field(default_factory=list)
    selected_new_items: List[HotlistItem] = field(default_factory=list)
    total_candidates: int = 0
    total_selected: int = 0
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.qualified_items and not self.selected_items:
            self.selected_items = list(self.qualified_items)
        elif self.selected_items and not self.qualified_items:
            self.qualified_items = list(self.selected_items)

        if self.qualified_items and self.total_selected <= 0:
            self.total_selected = len(self.qualified_items)

    def resolve_selected_new_items(self, snapshot_new_items: List[HotlistItem]) -> List[HotlistItem]:
        """Return snapshot new items after applying the selection-stage filter."""

        if not snapshot_new_items:
            return list(self.selected_new_items)
        effective_items = self.qualified_items or self.selected_items
        if not effective_items:
            return []

        selected_ids = {str(item.news_item_id) for item in effective_items}
        return [item for item in snapshot_new_items if str(item.news_item_id) in selected_ids]


@dataclass
class InsightResult:
    """Insight stage output shared with report assembly."""

    enabled: bool = False
    strategy: str = "noop"
    sections: List[InsightSection] = field(default_factory=list)
    item_analyses: List[Any] = field(default_factory=list)
    raw_response: str = ""
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportPackageMeta:
    """Metadata describing the assembled report package."""

    mode: str = ""
    report_type: str = ""
    generated_at: str = ""
    timezone: str = ""
    display_mode: str = "keyword"
    selection_strategy: str = ""
    insight_strategy: str = ""


@dataclass
class ReportContent:
    """Normalized report content that downstream presentation can consume directly."""

    hotlist_groups: List[SelectionGroup] = field(default_factory=list)
    selected_items: List[HotlistItem] = field(default_factory=list)
    new_items: List[HotlistItem] = field(default_factory=list)
    standalone_sections: List[StandaloneSection] = field(default_factory=list)
    insight_sections: List[InsightSection] = field(default_factory=list)


@dataclass
class ReportIntegrity:
    """Integrity and validation details for the assembled report package."""

    valid: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    skipped_regions: List[str] = field(default_factory=list)
    counters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportPackage:
    """Unified Stage 6 output assembled from snapshot, selection and insight."""

    meta: ReportPackageMeta = field(default_factory=ReportPackageMeta)
    content: ReportContent = field(default_factory=ReportContent)
    integrity: ReportIntegrity = field(default_factory=ReportIntegrity)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryPayload:
    """Final payload sent to a notification or delivery channel."""

    channel: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
