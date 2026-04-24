# coding=utf-8
"""Resolved runtime and request contracts for the provider-native AI runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolvedChatRuntime:
    """Concrete chat runtime chosen from a loose config mapping."""

    provider_family: str
    model: str
    request_model: str
    api_key: str = ""
    api_base: str = ""
    api_style: str = ""
    timeout: int = 120
    temperature: float = 1.0
    max_tokens: int = 5000
    num_retries: int = 2
    extra_params: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatRequest:
    """Normalized chat request sent to one provider-family runtime."""

    model: str
    messages: list[dict[str, Any]]
    response_mode: str = "native"
    json_schema: dict[str, Any] | None = None
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    api_key: str = ""
    api_base: str = ""
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedEmbeddingRuntime:
    """Concrete embedding runtime chosen from a loose config mapping."""

    provider_family: str
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
    """Normalized embedding request sent to one provider-family runtime."""

    model: str
    inputs: list[str]
    timeout: int = 120
    batch_size: int = 64
    api_key: str = ""
    api_base: str = ""
    extra_params: dict[str, Any] = field(default_factory=dict)
