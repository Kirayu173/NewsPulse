# coding=utf-8
"""Delivery-stage option builder."""

from __future__ import annotations

from newspulse.runtime.settings import RuntimeSettings
from newspulse.workflow.shared.options import DeliveryOptions


class DeliveryOptionsBuilder:
    """Build delivery options from runtime settings."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    def build(
        self,
        *,
        enabled: bool | None = None,
        channels: list[str] | None = None,
        dry_run: bool = False,
        proxy_url: str | None = None,
    ) -> DeliveryOptions:
        metadata: dict[str, str] = {}
        if proxy_url:
            metadata["proxy_url"] = proxy_url

        return DeliveryOptions(
            enabled=self.settings.delivery.enabled if enabled is None else enabled,
            channels=list(channels or self.settings.delivery.channels),
            dry_run=dry_run,
            metadata=metadata,
        )
