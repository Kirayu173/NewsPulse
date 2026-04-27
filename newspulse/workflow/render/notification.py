# coding=utf-8
"""Notification adapter for the workflow render stage."""

from __future__ import annotations

from typing import Any

from newspulse.workflow.render.models import RenderViewModel
from newspulse.workflow.render.notification_content import split_content_into_batches
from newspulse.workflow.shared.contracts import DeliveryPayload


class NotificationRenderAdapter:
    """Render native render view models into delivery payload batches."""

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
        self.region_order = list(region_order or ["hotlist", "new_items", "standalone", "insight"])
        self.display_mode = display_mode
        self.rank_threshold = rank_threshold
        self.batch_size = batch_size
        self.show_new_section = show_new_section

    def run(
        self,
        view_model: RenderViewModel,
        *,
        update_info: dict[str, Any] | None = None,
        region_order: list[str] | None = None,
        show_new_section: bool | None = None,
    ) -> list[DeliveryPayload]:
        """Render notification batches for the configured channels."""

        payloads: list[DeliveryPayload] = []
        if not self.notification_channels:
            return payloads
        effective_region_order = list(region_order or self.region_order)
        effective_show_new_section = self.show_new_section if show_new_section is None else show_new_section

        for channel in self.notification_channels:
            format_type = "wework" if channel == "generic_webhook" else channel
            batches = split_content_into_batches(
                view_model,
                format_type=format_type,
                update_info=update_info,
                max_bytes=self.batch_size,
                region_order=effective_region_order,
                get_time_func=self.get_time_func,
                show_new_section=effective_show_new_section,
            )
            total_batches = len(batches)
            for index, content in enumerate(batches, start=1):
                payloads.append(
                    DeliveryPayload(
                        channel=channel,
                        title=view_model.report_type,
                        content=content,
                        metadata={
                            "mode": view_model.mode,
                            "format_type": format_type,
                            "batch_index": index,
                            "batch_total": total_batches,
                        },
                    )
                )
        return payloads
