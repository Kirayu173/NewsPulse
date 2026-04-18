# coding=utf-8
"""Private models used by the workflow delivery stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChannelDeliveryResult:
    """Per-channel delivery summary."""

    channel: str
    attempted_payloads: int = 0
    delivered_payloads: int = 0
    success: bool = False
    skipped: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryResult:
    """Combined delivery-stage result."""

    success: bool = False
    attempted_payloads: int = 0
    delivered_payloads: int = 0
    channel_results: list[ChannelDeliveryResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
