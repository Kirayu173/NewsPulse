# coding=utf-8
"""Private models used by the render/report assembly stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from newspulse.workflow.shared.contracts import DeliveryPayload


DEFAULT_RENDER_REGIONS = [
    "hotlist",
    "new_items",
    "standalone",
    "ai_analysis",
]

REPORT_TYPE_BY_MODE = {
    "daily": "每日报告",
    "current": "实时报告",
    "incremental": "增量报告",
}


@dataclass(frozen=True)
class RenderReportMeta:
    """Normalized report metadata assembled before localization/rendering."""

    mode: str
    generated_at: str
    report_type: str
    timezone: str = ""
    display_mode: str = "keyword"
    selection_strategy: str = ""
    insight_strategy: str = ""
    total_items: int = 0
    total_selected: int = 0
    total_new_items: int = 0
    total_standalone_sections: int = 0
    total_failed_sources: int = 0
    snapshot_summary: dict[str, Any] = field(default_factory=dict)
    selection_diagnostics: dict[str, Any] = field(default_factory=dict)
    insight_diagnostics: dict[str, Any] = field(default_factory=dict)
    failed_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the normalized metadata to the public report shape."""

        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "report_type": self.report_type,
            "timezone": self.timezone,
            "display_mode": self.display_mode,
            "selection_strategy": self.selection_strategy,
            "insight_strategy": self.insight_strategy,
            "total_items": self.total_items,
            "total_selected": self.total_selected,
            "total_new_items": self.total_new_items,
            "total_standalone_sections": self.total_standalone_sections,
            "total_failed_sources": self.total_failed_sources,
            "snapshot_summary": dict(self.snapshot_summary),
            "selection_diagnostics": dict(self.selection_diagnostics),
            "insight_diagnostics": dict(self.insight_diagnostics),
            "failed_sources": [dict(item) for item in self.failed_sources],
        }


@dataclass(frozen=True)
class LegacyRenderContext:
    """Legacy adapter payload consumed by the current HTML and notification renderers."""

    report_data: dict[str, Any] = field(default_factory=dict)
    standalone_data: dict[str, Any] | None = None
    ai_analysis: Any = None
    total_titles: int = 0
    mode: str = "daily"
    report_type: str = "热点报告"


@dataclass(frozen=True)
class HTMLArtifact:
    """HTML render artifact produced by the render stage."""

    file_path: str = ""
    content: str = ""


@dataclass(frozen=True)
class RenderArtifacts:
    """Combined render outputs used by the downstream delivery stage."""

    html: HTMLArtifact = field(default_factory=HTMLArtifact)
    payloads: list[DeliveryPayload] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
