# coding=utf-8
"""Render-stage option builder."""

from __future__ import annotations

from typing import Any

from newspulse.runtime.settings import RuntimeSettings
from newspulse.workflow.shared.options import RenderOptions


class RenderOptionsBuilder:
    """Build render options from runtime settings."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    def build(
        self,
        *,
        emit_html: bool | None = None,
        emit_notification: bool | None = None,
        display_regions: list[str] | None = None,
        update_info: dict[str, Any] | None = None,
    ) -> RenderOptions:
        metadata: dict[str, Any] = {}
        if update_info:
            metadata["update_info"] = dict(update_info)

        return RenderOptions(
            display_regions=list(display_regions or self.settings.render.region_order),
            emit_html=True if emit_html is None else emit_html,
            emit_notification=bool(self.settings.delivery.channels) if emit_notification is None else emit_notification,
            metadata=metadata,
        )
