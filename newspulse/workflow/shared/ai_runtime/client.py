# coding=utf-8
"""Shared AI client used by workflow stages."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError

_CACHE_EXCLUDED_PARAM_KEYS = {"api_key", "timeout", "num_retries", "require_api_key"}


@dataclass(frozen=True)
class AIRuntimeConfig:
    """Normalized runtime configuration for LLM calls."""

    model: str = "deepseek/deepseek-chat"
    api_key: str = ""
    api_base: str = ""
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    fallback_models: list[str] = field(default_factory=list)

    @staticmethod
    def normalize_model(model: str, api_base: str = "") -> str:
        """Allow plain model names when using an OpenAI-compatible base URL."""

        normalized = (model or "").strip()
        if not normalized:
            return ""
        if "/" in normalized:
            return normalized
        if api_base:
            return f"openai/{normalized}"
        return normalized

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "AIRuntimeConfig":
        """Create a normalized runtime config from mixed-case config mappings."""

        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] is not None:
                    return config[name]
            return default

        api_key = pick("API_KEY", "api_key", default=os.environ.get("AI_API_KEY", ""))
        api_base = pick("API_BASE", "api_base", default="")
        model = cls.normalize_model(
            pick("MODEL", "model", default="deepseek/deepseek-chat"),
            api_base,
        )
        fallback_models = list(pick("FALLBACK_MODELS", "fallback_models", default=[]))
        return cls(
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=float(pick("TEMPERATURE", "temperature", default=1.0)),
            max_tokens=int(pick("MAX_TOKENS", "max_tokens", default=5000)),
            timeout=int(pick("TIMEOUT", "timeout", default=120)),
            num_retries=int(pick("NUM_RETRIES", "num_retries", default=2)),
            fallback_models=fallback_models,
        )

    def validate(self, *, require_api_key: bool = True) -> None:
        """Validate the runtime configuration and raise typed errors on failure."""

        if not self.model:
            raise AIConfigError("AI model is not configured")
        if require_api_key and not self.api_key:
            raise AIConfigError("AI API key is not configured")
        if "/" not in self.model:
            raise AIConfigError(
                "AI model must use provider/model format",
                details={"model": self.model},
            )

    def build_completion_params(
        self,
        messages: Iterable[dict[str, str]],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Build the LiteLLM completion payload for a chat request."""

        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "messages": list(messages),
            "temperature": overrides.get("temperature", self.temperature),
            "timeout": overrides.get("timeout", self.timeout),
            "num_retries": overrides.get("num_retries", self.num_retries),
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

        fallbacks = overrides.get("fallbacks", self.fallback_models)
        if fallbacks:
            params["fallbacks"] = list(fallbacks)

        passthrough_keys = set(params)
        for key, value in overrides.items():
            if key not in passthrough_keys:
                params[key] = value
        return params


class AIRuntimeClient:
    """Thin shared wrapper around LiteLLM chat completion."""

    def __init__(
        self,
        config: AIRuntimeConfig | Mapping[str, Any],
        *,
        completion_func: Callable[..., Any] | None = None,
    ):
        self.config = config if isinstance(config, AIRuntimeConfig) else AIRuntimeConfig.from_mapping(config)
        if completion_func is None:
            from litellm import completion as completion_func

        self._completion = completion_func

    def validate_config(self, *, require_api_key: bool = True) -> tuple[bool, str]:
        """Return validation status in the legacy tuple format."""

        try:
            self.config.validate(require_api_key=require_api_key)
        except AIConfigError as exc:
            return False, str(exc)
        return True, ""

    def build_completion_params(
        self,
        messages: Iterable[dict[str, str]],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Expose normalized request building for wrappers and diagnostics."""

        return self.config.build_completion_params(messages, **overrides)

    def chat(self, messages: list[dict[str, str]], **overrides: Any) -> str:
        """Call the configured model and normalize the returned content."""

        require_api_key = overrides.pop("require_api_key", True)
        self.config.validate(require_api_key=require_api_key)
        params = self.build_completion_params(messages, **overrides)

        try:
            response = self._completion(**params)
        except Exception as exc:
            raise AIInvocationError(
                "AI completion request failed",
                details={"model": params.get("model", "")},
            ) from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise AIInvocationError("AI completion response does not contain message content") from exc
        return coerce_text_content(content)


class CachedAIRuntimeClient:
    """In-memory TTL cache wrapper for repeated AI runtime requests."""

    def __init__(
        self,
        client: AIRuntimeClient | AIRuntimeConfig | Mapping[str, Any],
        *,
        completion_func: Callable[..., Any] | None = None,
        enabled: bool = True,
        ttl_seconds: int = 3600,
        max_entries: int = 1024,
        clock: Callable[[], float] | None = None,
    ):
        if isinstance(client, AIRuntimeClient):
            self._client = client
        else:
            self._client = AIRuntimeClient(client, completion_func=completion_func)
        self.enabled = bool(enabled)
        self.ttl_seconds = max(0, int(ttl_seconds or 0))
        self.max_entries = max(0, int(max_entries or 0))
        self._clock = clock or time.monotonic
        self._cache: dict[str, tuple[float, str]] = {}
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._evictions = 0

    @property
    def config(self) -> AIRuntimeConfig:
        return self._client.config

    def validate_config(self, *, require_api_key: bool = True) -> tuple[bool, str]:
        return self._client.validate_config(require_api_key=require_api_key)

    def build_completion_params(
        self,
        messages: Iterable[dict[str, str]],
        **overrides: Any,
    ) -> dict[str, Any]:
        return self._client.build_completion_params(messages, **overrides)

    def reset_cache(self) -> None:
        self._cache.clear()

    def cache_stats(self) -> dict[str, Any]:
        self._purge_expired()
        return {
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "stores": self._stores,
            "evictions": self._evictions,
        }

    def chat(self, messages: list[dict[str, str]], **overrides: Any) -> str:
        cache_enabled = overrides.pop("cache_enabled", self.enabled)
        cache_bypass = bool(overrides.pop("cache_bypass", False))
        cache_context = overrides.pop("cache_context", None)
        ttl_override = overrides.pop("cache_ttl_seconds", None)
        ttl_seconds = self.ttl_seconds if ttl_override is None else max(0, int(ttl_override or 0))

        if not cache_enabled or cache_bypass or ttl_seconds <= 0 or self.max_entries <= 0:
            return self._client.chat(messages, **overrides)

        now = self._clock()
        self._purge_expired(now)
        cache_key = self._build_cache_key(messages, overrides, cache_context)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > now:
            self._hits += 1
            return cached[1]

        self._misses += 1
        response = self._client.chat(messages, **overrides)
        self._store(cache_key, response, ttl_seconds, now)
        return response

    def _store(self, cache_key: str, response: str, ttl_seconds: int, now: float) -> None:
        if cache_key in self._cache:
            self._cache.pop(cache_key, None)
        while len(self._cache) >= self.max_entries:
            oldest_key = next(iter(self._cache), None)
            if oldest_key is None:
                break
            self._cache.pop(oldest_key, None)
            self._evictions += 1
        self._cache[cache_key] = (now + ttl_seconds, response)
        self._stores += 1

    def _purge_expired(self, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        expired_keys = [key for key, (expires_at, _) in self._cache.items() if expires_at <= now]
        for key in expired_keys:
            self._cache.pop(key, None)
        self._evictions += len(expired_keys)

    def _build_cache_key(
        self,
        messages: Iterable[dict[str, str]],
        overrides: Mapping[str, Any],
        cache_context: Any,
    ) -> str:
        normalized_messages = [_normalize_message(message) for message in messages]
        params = self.build_completion_params(normalized_messages, **overrides)
        key_payload = {
            "model": str(params.get("model", "") or ""),
            "messages": normalized_messages,
            "params": {
                str(key): _normalize_cache_value(value)
                for key, value in params.items()
                if key not in _CACHE_EXCLUDED_PARAM_KEYS and key != "messages"
            },
        }
        if cache_context is not None:
            key_payload["cache_context"] = _normalize_cache_value(cache_context)
        raw_key = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _normalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in sorted(message.items(), key=lambda item: str(item[0])):
        normalized_key = str(key)
        if normalized_key == "content":
            normalized[normalized_key] = coerce_text_content(value)
        else:
            normalized[normalized_key] = _normalize_cache_value(value)
    return normalized


def _normalize_cache_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_cache_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_cache_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
