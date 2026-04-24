# coding=utf-8
"""Structured request/response and resolved runtime contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolvedChatRuntime:
    """Concrete chat runtime chosen from a loose config mapping."""

    driver: str
    model: str
    request_model: str
    api_key: str = ""
    api_base: str = ""
    api_style: str = ""
    timeout: int = 120
    temperature: float = 1.0
    max_tokens: int = 5000
    num_retries: int = 2
    fallback_models: tuple[str, ...] = ()
    extra_params: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatRequest:
    """Normalized chat request sent to one adapter."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    api_key: str = ""
    api_base: str = ""
    driver: str = ""
    fallbacks: tuple[str, ...] = ()
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResponse:
    """Normalized chat response returned by every adapter."""

    text: str
    raw_text: str = ""
    finish_reason: str = ""
    provider_message: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedEmbeddingRuntime:
    """Concrete embedding runtime chosen from a loose config mapping."""

    driver: str
    model: str
    request_model: str
    api_key: str = ""
    api_base: str = ""
    api_style: str = ""
    timeout: int = 120
    batch_size: int = 64
    enabled: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingRequest:
    """Normalized embedding request sent to one adapter."""

    model: str
    inputs: list[str]
    timeout: int = 120
    batch_size: int = 64
    api_key: str = ""
    api_base: str = ""
    driver: str = ""
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResponse:
    """Normalized embedding response returned by every adapter."""

    vectors: list[list[float]]
    diagnostics: dict[str, Any] = field(default_factory=dict)
