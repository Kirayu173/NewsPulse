# coding=utf-8
"""Notification adapter for the workflow render stage."""

from __future__ import annotations

from typing import Any

from newspulse.notification import split_content_into_batches
from newspulse.workflow.render.models import LegacyRenderContext
from newspulse.workflow.shared.contracts import DeliveryPayload, LocalizedReport


class NotificationRenderAdapter:
    """Render localized workflow reports into delivery payload batches."""

    def __init__(
        self,
        *,
        notification_channels: list[str] | None = None,
        get_time_func=None,
        region_order: list[str] | None = None,
        display_mode: str = "keyword",
        rank_threshold: int = 10,
        batch_size: int = 4000,
        show_new_section: bool = True,
    ):
        self.notification_channels = list(notification_channels or [])
        self.get_time_func = get_time_func
        self.region_order = list(region_order or ["hotlist", "new_items", "standalone", "ai_analysis"])
        self.display_mode = display_mode
        self.rank_threshold = rank_threshold
        self.batch_size = batch_size
        self.show_new_section = show_new_section

    def run(
        self,
        report: LocalizedReport,
        legacy_context: LegacyRenderContext,
        *,
        update_info: dict[str, Any] | None = None,
        region_order: list[str] | None = None,
        show_new_section: bool | None = None,
    ) -> list[DeliveryPayload]:
        """Render notification batches for the configured channels."""

        del report
        payloads: list[DeliveryPayload] = []
        if not self.notification_channels:
            return payloads
        effective_region_order = list(region_order or self.region_order)
        effective_show_new_section = self.show_new_section if show_new_section is None else show_new_section

        ai_content = ""
        ai_stats = None
        if legacy_context.ai_analysis:
            from newspulse.ai.formatter import render_ai_analysis_markdown

            ai_content = render_ai_analysis_markdown(legacy_context.ai_analysis)
            if getattr(legacy_context.ai_analysis, "success", False):
                ai_stats = {
                    "total_news": getattr(legacy_context.ai_analysis, "total_news", 0),
                    "analyzed_news": getattr(legacy_context.ai_analysis, "analyzed_news", 0),
                    "max_news_limit": getattr(legacy_context.ai_analysis, "max_news_limit", 0),
                    "hotlist_count": getattr(legacy_context.ai_analysis, "hotlist_count", 0),
                    "ai_mode": getattr(legacy_context.ai_analysis, "ai_mode", ""),
                }

        for channel in self.notification_channels:
            format_type = "wework" if channel == "generic_webhook" else channel
            batches = split_content_into_batches(
                report_data=legacy_context.report_data,
                format_type=format_type,
                update_info=update_info,
                max_bytes=self.batch_size,
                mode=legacy_context.mode,
                region_order=effective_region_order,
                get_time_func=self.get_time_func,
                display_mode=self.display_mode,
                ai_content=ai_content,
                standalone_data=legacy_context.standalone_data,
                rank_threshold=self.rank_threshold,
                ai_stats=ai_stats,
                report_type=legacy_context.report_type,
                show_new_section=effective_show_new_section,
            )
            total_batches = len(batches)
            for index, content in enumerate(batches, start=1):
                payloads.append(
                    DeliveryPayload(
                        channel=channel,
                        title=legacy_context.report_type,
                        content=content,
                        metadata={
                            "mode": legacy_context.mode,
                            "format_type": format_type,
                            "batch_index": index,
                            "batch_total": total_batches,
                        },
                    )
                )
        return payloads
