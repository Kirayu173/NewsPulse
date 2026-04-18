# coding=utf-8
"""Delivery stage service."""

from __future__ import annotations

from typing import Sequence

from newspulse.workflow.delivery.generic_webhook import GenericWebhookDeliveryAdapter
from newspulse.workflow.delivery.models import ChannelDeliveryResult, DeliveryResult
from newspulse.workflow.shared.contracts import DeliveryPayload
from newspulse.workflow.shared.options import DeliveryOptions


class DeliveryService:
    """Deliver prepared workflow payloads to external channels."""

    def __init__(
        self,
        *,
        generic_webhook_adapter: GenericWebhookDeliveryAdapter | None = None,
    ):
        self.generic_webhook_adapter = generic_webhook_adapter

    def run(self, payloads: Sequence[DeliveryPayload], options: DeliveryOptions) -> DeliveryResult:
        """Run the delivery stage."""

        payload_list = list(payloads)
        if not options.enabled:
            return DeliveryResult(
                success=False,
                attempted_payloads=len(payload_list),
                delivered_payloads=0,
                metadata={"skipped": True, "reason": "delivery disabled"},
            )

        allowed_channels = {channel for channel in options.channels if channel} or {
            payload.channel for payload in payload_list if payload.channel
        }
        channel_results: list[ChannelDeliveryResult] = []
        for channel in sorted(allowed_channels):
            channel_payloads = [payload for payload in payload_list if payload.channel == channel]
            if channel == "generic_webhook":
                if self.generic_webhook_adapter is None:
                    channel_results.append(
                        ChannelDeliveryResult(
                            channel=channel,
                            attempted_payloads=len(channel_payloads),
                            success=False,
                            metadata={"reason": "missing adapter"},
                        )
                    )
                else:
                    channel_results.append(
                        self.generic_webhook_adapter.run(
                            channel_payloads,
                            proxy_url=str(options.metadata.get("proxy_url") or "") or None,
                            dry_run=options.dry_run,
                        )
                    )
                continue

            channel_results.append(
                ChannelDeliveryResult(
                    channel=channel,
                    attempted_payloads=len(channel_payloads),
                    success=False,
                    skipped=not channel_payloads,
                    metadata={"reason": "unsupported channel"},
                )
            )

        delivered_payloads = sum(result.delivered_payloads for result in channel_results)
        attempted_payloads = sum(result.attempted_payloads for result in channel_results)
        success = any(result.success for result in channel_results)
        return DeliveryResult(
            success=success,
            attempted_payloads=attempted_payloads,
            delivered_payloads=delivered_payloads,
            channel_results=channel_results,
            metadata={
                "channel_count": len(channel_results),
                "dry_run": options.dry_run,
            },
        )
