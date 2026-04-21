# coding=utf-8
"""Render stage service."""

from __future__ import annotations

from newspulse.utils.time import convert_time_for_display
from newspulse.workflow.render.html import HTMLRenderAdapter
from newspulse.workflow.render.models import HTMLArtifact, RenderArtifacts, build_render_view_model
from newspulse.workflow.render.notification import NotificationRenderAdapter
from newspulse.workflow.shared.contracts import ReportPackage
from newspulse.workflow.shared.options import RenderOptions


class RenderService:
    """Render report packages into HTML and delivery payloads."""

    def __init__(
        self,
        *,
        html_adapter: HTMLRenderAdapter | None = None,
        notification_adapter: NotificationRenderAdapter | None = None,
        display_mode: str = "keyword",
        rank_threshold: int = 50,
        weight_config: dict[str, float] | None = None,
    ):
        self.html_adapter = html_adapter or HTMLRenderAdapter(display_mode=display_mode)
        self.notification_adapter = notification_adapter or NotificationRenderAdapter(
            display_mode=display_mode,
            rank_threshold=rank_threshold,
        )
        self.display_mode = display_mode
        self.rank_threshold = rank_threshold
        self.weight_config = weight_config or {}

    def run(self, report: ReportPackage, options: RenderOptions) -> RenderArtifacts:
        """Run the render stage directly from the Stage 6 report package."""

        region_order = self._resolve_region_order(options)
        show_new_section = "new_items" in region_order
        view_model = build_render_view_model(
            report,
            display_mode=self.display_mode,
            rank_threshold=self.rank_threshold,
            weight_config=self.weight_config,
            convert_time_func=convert_time_for_display,
        )
        update_info = options.metadata.get("update_info")

        html_artifact = (
            self.html_adapter.run(
                view_model,
                update_info=update_info,
                region_order=region_order,
                show_new_section=show_new_section,
            )
            if options.emit_html
            else None
        )
        payloads = (
            self.notification_adapter.run(
                view_model,
                update_info=update_info,
                region_order=region_order,
                show_new_section=show_new_section,
            )
            if options.emit_notification
            else []
        )

        metadata = {
            "mode": view_model.mode,
            "report_type": view_model.report_type,
            "display_regions": list(region_order),
            "payload_count": len(payloads),
            "html_enabled": options.emit_html,
            "notification_enabled": options.emit_notification,
            "integrity_valid": report.integrity.valid,
            "integrity_warning_count": len(report.integrity.warnings),
            "integrity_error_count": len(report.integrity.errors),
        }
        if html_artifact is not None:
            metadata["html_file_path"] = html_artifact.file_path

        return RenderArtifacts(
            html=html_artifact or HTMLArtifact(),
            payloads=payloads,
            metadata=metadata,
        )

    @staticmethod
    def _resolve_region_order(options: RenderOptions) -> list[str]:
        normalized: list[str] = []
        for value in options.display_regions:
            region = str(value or "").strip().lower()
            if region and region not in normalized:
                normalized.append(region)
        if normalized:
            return normalized
        if options.display_regions:
            return []
        return ["hotlist", "new_items", "standalone", "insight"]
