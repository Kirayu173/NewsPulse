# coding=utf-8
"""Stage options shared by the native workflow pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SnapshotOptions:
    """Options for building the normalized downstream snapshot."""

    mode: str = "current"
    schedule: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionAIOptions:
    """Nested AI options for the selection stage."""

    interests_file: str = "ai_interests.txt"
    batch_size: int = 50
    batch_interval: float = 2.0
    min_score: float = 0.7
    fallback_to_keyword: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionOptions:
    """Options for the selection stage."""

    strategy: str = "keyword"
    frequency_file: Optional[str] = None
    priority_sort_enabled: bool = False
    ai: SelectionAIOptions = field(default_factory=SelectionAIOptions)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InsightOptions:
    """Options for the insight stage."""

    enabled: bool = False
    strategy: str = "noop"
    mode: str = "follow_report"
    max_items: int = 150
    include_standalone: bool = True
    include_rank_timeline: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalizationScope:
    """Fine-grained scope switches for localization."""

    selection_titles: bool = True
    new_items: bool = True
    standalone: bool = True
    insight_sections: bool = False


@dataclass
class LocalizationOptions:
    """Options for the localization stage."""

    enabled: bool = False
    strategy: str = "noop"
    language: str = "Chinese"
    scope: LocalizationScope = field(default_factory=LocalizationScope)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderOptions:
    """Options for the render stage."""

    display_regions: List[str] = field(
        default_factory=lambda: ["hotlist", "new_items", "standalone", "ai_analysis"]
    )
    emit_html: bool = True
    emit_notification: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryOptions:
    """Options for the delivery stage."""

    enabled: bool = True
    channels: List[str] = field(default_factory=list)
    dry_run: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowOptions:
    """Top-level workflow options bundle used by the orchestrator."""

    snapshot: SnapshotOptions = field(default_factory=SnapshotOptions)
    selection: SelectionOptions = field(default_factory=SelectionOptions)
    insight: InsightOptions = field(default_factory=InsightOptions)
    localization: LocalizationOptions = field(default_factory=LocalizationOptions)
    render: RenderOptions = field(default_factory=RenderOptions)
    delivery: DeliveryOptions = field(default_factory=DeliveryOptions)
