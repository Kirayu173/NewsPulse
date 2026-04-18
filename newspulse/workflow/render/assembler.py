# coding=utf-8
"""Renderable report assembler for the native workflow pipeline."""

from __future__ import annotations

from typing import Iterable

from newspulse.workflow.render.models import (
    DEFAULT_RENDER_REGIONS,
    REPORT_TYPE_BY_MODE,
    RenderReportMeta,
)
from newspulse.workflow.shared.contracts import HotlistSnapshot, InsightResult, RenderableReport, SelectionResult


class HotlistReportAssembler:
    """Assemble snapshot, selection and insight outputs into a single report object."""

    def __init__(
        self,
        *,
        display_regions: Iterable[str] | None = None,
        timezone: str = "",
        display_mode: str = "keyword",
    ):
        self.display_regions = self._normalize_display_regions(display_regions)
        self.timezone = timezone
        self.display_mode = display_mode

    def assemble(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
    ) -> RenderableReport:
        """Combine stage outputs into a renderable report payload."""

        selected_new_items = selection.resolve_selected_new_items(snapshot.new_items)
        selection.selected_new_items = list(selected_new_items)
        meta = RenderReportMeta(
            mode=snapshot.mode,
            generated_at=snapshot.generated_at,
            report_type=REPORT_TYPE_BY_MODE.get(snapshot.mode, "热点分析报告"),
            timezone=self.timezone,
            display_mode=self.display_mode,
            selection_strategy=selection.strategy,
            insight_strategy=insight.strategy,
            total_items=snapshot.item_count,
            total_selected=selection.total_selected,
            total_new_items=len(selected_new_items),
            total_standalone_sections=len(snapshot.standalone_sections),
            total_failed_sources=len(snapshot.failed_sources),
            snapshot_summary=dict(snapshot.summary),
            selection_diagnostics=dict(selection.diagnostics),
            insight_diagnostics=dict(insight.diagnostics),
            failed_sources=[
                {
                    "source_id": item.source_id,
                    "source_name": item.source_name,
                    "reason": item.reason,
                }
                for item in snapshot.failed_sources
            ],
        )
        return RenderableReport(
            meta=meta.to_dict(),
            selection=selection,
            insight=insight,
            new_items=list(selected_new_items),
            standalone_sections=list(snapshot.standalone_sections),
            display_regions=list(self.display_regions),
        )

    @staticmethod
    def _normalize_display_regions(display_regions: Iterable[str] | None) -> list[str]:
        normalized: list[str] = []
        for value in display_regions or DEFAULT_RENDER_REGIONS:
            region = str(value or "").strip().lower()
            if region and region not in normalized:
                normalized.append(region)
        return normalized or list(DEFAULT_RENDER_REGIONS)
