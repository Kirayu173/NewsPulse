# coding=utf-8
"""Workflow stage contracts for the native hotlist pipeline."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from newspulse.workflow.delivery import (
    ChannelDeliveryResult,
    DeliveryResult,
    DeliveryService,
    GenericWebhookDeliveryAdapter,
)
from newspulse.workflow.report import ReportPackageAssembler, ReportPackageValidator
from newspulse.workflow.render import (
    HTMLArtifact,
    HTMLRenderAdapter,
    NotificationRenderAdapter,
    RenderArtifacts,
    RenderService,
    RenderViewModel,
    build_render_view_model,
    render_hotlist_stats_html,
    split_content_into_batches,
)
from newspulse.workflow.shared.contracts import (
    DeliveryPayload,
    HotlistItem,
    HotlistSnapshot,
    InsightResult,
    InsightSection,
    ReportContent,
    ReportIntegrity,
    ReportPackage,
    ReportPackageMeta,
    SelectionGroup,
    SelectionRejectedItem,
    SelectionResult,
    SourceFailure,
    StandaloneSection,
)
from newspulse.workflow.shared.options import (
    DeliveryOptions,
    InsightOptions,
    RenderOptions,
    SelectionAIOptions,
    SelectionOptions,
    SelectionSemanticOptions,
    SnapshotOptions,
    WorkflowOptions,
)

WORKFLOW_STAGE_NAMES = (
    "snapshot",
    "selection",
    "insight",
    "report",
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
    """Assemble the Stage 6 report package from stage outputs."""

    def assemble(
        self,
        snapshot: HotlistSnapshot,
        selection: SelectionResult,
        insight: InsightResult,
    ) -> ReportPackage:
        """Combine stage outputs into a report package."""


@runtime_checkable
class RenderStage(Protocol):
    """Render a report package into downstream artifacts."""

    def run(self, report: ReportPackage, options: RenderOptions) -> object:
        """Render the report package into downstream artifacts."""


@runtime_checkable
class DeliveryStage(Protocol):
    """Deliver prepared payloads to the configured notification channels."""

    def run(self, payloads: Sequence[DeliveryPayload], options: DeliveryOptions) -> object:
        """Send prepared payloads to external channels."""


__all__ = [
    "WORKFLOW_STAGE_NAMES",
    "ChannelDeliveryResult",
    "DeliveryOptions",
    "DeliveryPayload",
    "DeliveryResult",
    "DeliveryService",
    "DeliveryStage",
    "GenericWebhookDeliveryAdapter",
    "HTMLArtifact",
    "HTMLRenderAdapter",
    "HotlistItem",
    "HotlistSnapshot",
    "InsightOptions",
    "InsightResult",
    "InsightSection",
    "InsightStage",
    "NotificationRenderAdapter",
    "RenderArtifacts",
    "RenderOptions",
    "RenderService",
    "RenderStage",
    "RenderViewModel",
    "ReportAssembler",
    "ReportContent",
    "ReportIntegrity",
    "ReportPackage",
    "ReportPackageAssembler",
    "ReportPackageMeta",
    "ReportPackageValidator",
    "SelectionAIOptions",
    "SelectionGroup",
    "SelectionOptions",
    "SelectionRejectedItem",
    "SelectionResult",
    "SelectionSemanticOptions",
    "SelectionStage",
    "SnapshotBuilder",
    "SnapshotOptions",
    "SourceFailure",
    "StandaloneSection",
    "WorkflowOptions",
    "build_render_view_model",
    "render_hotlist_stats_html",
    "split_content_into_batches",
]
