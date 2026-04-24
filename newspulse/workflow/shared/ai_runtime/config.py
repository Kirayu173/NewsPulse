# coding=utf-8
"""Runtime configuration models for the provider-native AI runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from newspulse.workflow.shared.ai_runtime.contracts import ResolvedChatRuntime, ResolvedEmbeddingRuntime
from newspulse.workflow.shared.ai_runtime.resolver import (
    normalize_model,
    resolve_chat_runtime,
    resolve_embedding_runtime,
    validate_chat_runtime,
    validate_embedding_runtime,
)


@dataclass(frozen=True)
class AIRuntimeConfig:
    """Normalized runtime configuration for chat generation."""

    model: str = ""
    api_key: str = ""
    api_base: str = ""
    provider_family: str = "auto"
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    extra_params: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def normalize_model(model: str, api_base: str = "", provider_family: str = "auto") -> str:
        return normalize_model(model, api_base=api_base, provider_family=provider_family)

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "AIRuntimeConfig":
        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] is not None:
                    return config[name]
            return default

        provider_family = str(
            pick("PROVIDER_FAMILY", "provider_family", default="auto") or "auto"
        )
        api_base = str(pick("API_BASE", "api_base", default="") or "")
        raw_model = str(pick("MODEL", "model", default="") or "").strip()
        model = raw_model
        if raw_model and "/" not in raw_model and (api_base or provider_family != "auto"):
            model = cls.normalize_model(
                raw_model,
                api_base=api_base,
                provider_family=provider_family,
            )
        return cls(
            model=model,
            api_key=str(pick("API_KEY", "api_key", default="") or ""),
            api_base=api_base,
            provider_family=provider_family,
            temperature=_coerce_number(pick("TEMPERATURE", "temperature", default=1.0), default=1.0, cast=float),
            max_tokens=_coerce_number(pick("MAX_TOKENS", "max_tokens", default=5000), default=5000, cast=int),
            timeout=_coerce_number(pick("TIMEOUT", "timeout", default=120), default=120, cast=int),
            num_retries=_coerce_number(pick("NUM_RETRIES", "num_retries", default=2), default=2, cast=int),
            extra_params=dict(pick("EXTRA_PARAMS", "extra_params", default={}) or {}),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "MODEL": self.model,
            "API_KEY": self.api_key,
            "API_BASE": self.api_base,
            "PROVIDER_FAMILY": self.provider_family,
            "TEMPERATURE": self.temperature,
            "MAX_TOKENS": self.max_tokens,
            "TIMEOUT": self.timeout,
            "NUM_RETRIES": self.num_retries,
            "EXTRA_PARAMS": dict(self.extra_params),
        }

    def resolve_runtime(self) -> ResolvedChatRuntime:
        return ResolvedChatRuntime(**resolve_chat_runtime(self.to_mapping()))

    def validate(self, *, require_api_key: bool = True) -> None:
        validate_chat_runtime(self.to_mapping(), require_api_key=require_api_key)

    def build_completion_params(self, messages: Iterable[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "messages": list(messages),
            "temperature": overrides.get("temperature", self.temperature),
            "timeout": overrides.get("timeout", self.timeout),
            "num_retries": overrides.get("num_retries", self.num_retries),
            "provider_family": overrides.get("provider_family", self.provider_family),
        }
        api_key = overrides.get("api_key", self.api_key)
        if api_key:
            params["api_key"] = api_key
        api_base = overrides.get("api_base", self.api_base)
        if api_base:
            params["api_base"] = api_base
        max_tokens = overrides.get("max_tokens", self.max_tokens)
        if max_tokens and max_tokens > 0:
            params["max_tokens"] = max_tokens

        merged_extra = dict(self.extra_params)
        override_extra = overrides.pop("extra_params", None)
        if isinstance(override_extra, Mapping):
            merged_extra.update(dict(override_extra))
        for key, value in merged_extra.items():
            params.setdefault(str(key), value)

        passthrough_keys = set(params)
        for key, value in overrides.items():
            if key not in passthrough_keys:
                params[key] = value
        return params


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    """Normalized runtime configuration for embedding requests."""

    model: str = ""
    api_key: str = ""
    api_base: str = ""
    provider_family: str = "openai"
    timeout: int = 120
    batch_size: int = 64
    extra_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "EmbeddingRuntimeConfig":
        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] not in (None, ""):
                    return config[name]
            return default

        api_base = str(pick("API_BASE", "api_base", default="") or "")
        raw_model = str(pick("MODEL", "model", default="") or "").strip()
        model = raw_model
        if raw_model and "/" not in raw_model and api_base:
            model = normalize_model(
                raw_model,
                api_base=api_base,
                provider_family="openai",
            )
        return cls(
            model=model,
            api_key=str(pick("API_KEY", "api_key", default="") or ""),
            api_base=api_base,
            provider_family="openai",
            timeout=_coerce_number(pick("TIMEOUT", "timeout", default=120), default=120, cast=int),
            batch_size=_coerce_number(pick("BATCH_SIZE", "batch_size", default=64), default=64, cast=int),
            extra_params=dict(pick("EXTRA_PARAMS", "extra_params", default={}) or {}),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "MODEL": self.model,
            "API_KEY": self.api_key,
            "API_BASE": self.api_base,
            "PROVIDER_FAMILY": self.provider_family,
            "TIMEOUT": self.timeout,
            "BATCH_SIZE": self.batch_size,
            "EXTRA_PARAMS": dict(self.extra_params),
        }

    def resolve_runtime(self) -> ResolvedEmbeddingRuntime:
        return ResolvedEmbeddingRuntime(**resolve_embedding_runtime(self.to_mapping()))

    def validate(self, *, require_api_key: bool = True) -> None:
        validate_embedding_runtime(self.to_mapping(), require_api_key=require_api_key)

    def build_embedding_params(self, inputs: Sequence[str], **overrides: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "input": list(inputs),
            "timeout": overrides.get("timeout", self.timeout),
            "provider_family": "openai",
        }
        api_key = overrides.get("api_key", self.api_key)
        if api_key:
            params["api_key"] = api_key
        api_base = overrides.get("api_base", self.api_base)
        if api_base:
            params["api_base"] = api_base

        passthrough = dict(self.extra_params)
        override_extra = overrides.get("extra_params", {})
        if isinstance(override_extra, Mapping):
            passthrough.update(dict(override_extra))
        for key, value in passthrough.items():
            if key not in params and value is not None:
                params[key] = value
        return params


def _coerce_number(value: Any, *, default: Any, cast: Any) -> Any:
    if value in (None, ""):
        return cast(default)
    return cast(value)
