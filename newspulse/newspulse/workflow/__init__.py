# coding=utf-8
"""Workflow stage contracts for the native hotlist pipeline."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from newspulse.workflow.shared.contracts import (
    DeliveryPayload,
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    LocalizedReport,
    RenderableReport,
    SelectionGroup,
    SelectionResult,
    SourceFailure,
    StandaloneSection,
)
from newspulse.workflow.shared.options import (
    DeliveryOptions,
    InsightOptions,
    LocalizationOptions,
    LocalizationScope,
    RenderOptions,
    SelectionAIOptions,
    SelectionOptions,
    SnapshotOptions,
    WorkflowOptions,
)
from newspulse.workflow.render import HotlistReportAssembler, RenderReportMeta

WORKFLOW_STAGE_NAMES = (
    "snapshot",
    "selection",
    "insight",
    "localization",
    "render",
    "delivery",
)


@runtime_checkable
class SnapshotBuilder(Protocol):
    """Build the unique snapshot input used by the downstream workflow."""

    def build(self, options: SnapshotOptions) -> HotlistSnapshot:
        """Produce the normalized snapshot for the downstream stages."""


@runtime_checkable
class SelectionStage(Protocol):
    """Select the hotlist items that enter the report pipeline."""

    def run(self, snapshot: HotlistSnapshot, options: SelectionOptions) -> SelectionResult:
        """Execute the selection strategy for the current snapshot."""


@runtime_checkable
class InsightStage(Protocol):
    """Generate higher-level insights from the selected hotlist items."""

    def run(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        options: InsightOptions,
    ) -> InsightResult:
        """Execute the insight strategy for the current snapshot."""


@runtime_checkable
class ReportAssembler(Protocol):
    """Assemble a render-ready report object from stage outputs."""

    def assemble(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
    ) -> RenderableReport:
        """Combine stage outputs into a renderable report."""


@runtime_checkable
class LocalizationStage(Protocol):
    """Localize a renderable report before rendering and delivery."""

    def run(self, report: RenderableReport, options: LocalizationOptions) -> LocalizedReport:
        """Execute report localization."""


@runtime_checkable
class RenderStage(Protocol):
    """Render a localized report into HTML and delivery artifacts."""

    def run(self, report: LocalizedReport, options: RenderOptions) -> object:
        """Render the localized report into downstream artifacts."""


@runtime_checkable
class DeliveryStage(Protocol):
    """Deliver prepared payloads to the configured notification channels."""

    def run(self, payloads: Sequence[DeliveryPayload], options: DeliveryOptions) -> object:
        """Send prepared payloads to external channels."""


__all__ = [
    "WORKFLOW_STAGE_NAMES",
    "DeliveryOptions",
    "DeliveryPayload",
    "DeliveryStage",
    "HotlistItem",
    "HotlistSnapshot",
    "HotlistReportAssembler",
    "InsightOptions",
    "InsightResult",
    "InsightSection",
    "InsightStage",
    "LocalizationOptions",
    "LocalizationScope",
    "LocalizationStage",
    "LocalizedReport",
    "RenderOptions",
    "RenderReportMeta",
    "RenderStage",
    "RenderableReport",
    "ReportAssembler",
    "SelectionAIOptions",
    "SelectionGroup",
    "SelectionOptions",
    "SelectionResult",
    "SelectionStage",
    "SnapshotBuilder",
    "SnapshotOptions",
    "SourceFailure",
    "StandaloneSection",
    "WorkflowOptions",
]
