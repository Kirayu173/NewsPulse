# coding=utf-8
"""Structured result models returned by the provider-native AI runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AIUsage:
    """Token-usage details returned by one provider invocation."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIBlock:
    """One native provider block preserved on the unified result."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIResult:
    """Unified chat result that preserves provider-native details."""

    provider_family: str
    model: str
    text: str = ""
    json_payload: Any | None = None
    blocks: tuple[AIBlock, ...] = ()
    thinking_blocks: tuple[AIBlock, ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    finish_reason: str = ""
    usage: AIUsage | None = None
    provider_response: Any | None = None
    continuation_payload: Any | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResult:
    """Unified embedding result for OpenAI-compatible embedding providers."""

    provider_family: str
    model: str
    vectors: tuple[tuple[float, ...], ...] = ()
    usage: AIUsage | None = None
    provider_response: Any | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
