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
from newspulse.workflow.shared.ai_runtime.contracts import ChatRequest, ResolvedChatRuntime
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError
from newspulse.workflow.shared.ai_runtime.resolver import normalize_model, resolve_chat_runtime, runtime_summary, validate_chat_runtime
from newspulse.workflow.shared.ai_runtime.adapters.anthropic_chat import AnthropicChatAdapter
from newspulse.workflow.shared.ai_runtime.adapters.litellm_chat import LiteLLMChatAdapter
from newspulse.workflow.shared.ai_runtime.adapters.openai_chat import OpenAIChatAdapter

_CACHE_EXCLUDED_PARAM_KEYS = {"api_key", "timeout", "num_retries", "require_api_key"}


@dataclass(frozen=True)
class AIRuntimeConfig:
    """Normalized runtime configuration for LLM calls."""

    model: str = "deepseek/deepseek-chat"
    api_key: str = ""
    api_base: str = ""
    driver: str = "auto"
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    fallback_models: list[str] = field(default_factory=list)
    extra_params: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def normalize_model(model: str, api_base: str = "", driver: str = "auto") -> str:
        """Allow plain model names when using an OpenAI/Anthropic-compatible base URL."""

        return normalize_model(model, api_base=api_base, driver=driver)

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "AIRuntimeConfig":
        """Create a normalized runtime config from mixed-case config mappings."""

        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] is not None:
                    return config[name]
            return default

        driver = str(
            pick(
                "DRIVER",
                "driver",
                default=os.environ.get("AI_DRIVER", os.environ.get("DRIVER", "auto")),
            )
            or "auto"
        )
        api_key = str(
            pick(
                "API_KEY",
                "api_key",
                default=os.environ.get("AI_API_KEY", os.environ.get("API_KEY", "")),
            )
            or ""
        )
        api_base = str(
            pick(
                "API_BASE",
                "api_base",
                default=os.environ.get(
                    "AI_API_BASE",
                    os.environ.get("AI_BASE_URL", os.environ.get("BASE_URL", os.environ.get("API_BASE", ""))),
                ),
            )
            or ""
        )
        model = cls.normalize_model(
            str(
                pick(
                    "MODEL",
                    "model",
                    default=os.environ.get("AI_MODEL", os.environ.get("MODEL", "deepseek/deepseek-chat")),
                )
                or ""
            ),
            api_base,
            driver,
        )
        fallback_models = list(pick("FALLBACK_MODELS", "fallback_models", default=[]))
        extra_params = dict(pick("EXTRA_PARAMS", "extra_params", default={}) or {})
        return cls(
            model=model,
            api_key=api_key,
            api_base=api_base,
            driver=driver,
            temperature=float(pick("TEMPERATURE", "temperature", default=1.0)),
            max_tokens=int(pick("MAX_TOKENS", "max_tokens", default=5000)),
            timeout=int(pick("TIMEOUT", "timeout", default=120)),
            num_retries=int(pick("NUM_RETRIES", "num_retries", default=2)),
            fallback_models=fallback_models,
            extra_params=extra_params,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "MODEL": self.model,
            "API_KEY": self.api_key,
            "API_BASE": self.api_base,
            "DRIVER": self.driver,
            "TEMPERATURE": self.temperature,
            "MAX_TOKENS": self.max_tokens,
            "TIMEOUT": self.timeout,
            "NUM_RETRIES": self.num_retries,
            "FALLBACK_MODELS": list(self.fallback_models),
            "EXTRA_PARAMS": dict(self.extra_params),
        }

    def resolve_runtime(self) -> ResolvedChatRuntime:
        runtime = resolve_chat_runtime(self.to_mapping())
        return ResolvedChatRuntime(**runtime)

    def validate(self, *, require_api_key: bool = True) -> None:
        """Validate the runtime configuration and raise typed errors on failure."""

        validate_chat_runtime(self.to_mapping(), require_api_key=require_api_key)

    def build_completion_params(
        self,
        messages: Iterable[dict[str, Any]],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Build the normalized chat payload for one request."""

        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "messages": list(messages),
            "temperature": overrides.get("temperature", self.temperature),
            "timeout": overrides.get("timeout", self.timeout),
            "num_retries": overrides.get("num_retries", self.num_retries),
            "driver": overrides.get("driver", self.driver),
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


class AIRuntimeClient:
    """Unified chat runtime wrapper around LiteLLM, OpenAI SDK, and Anthropic SDK."""

    def __init__(
        self,
        config: AIRuntimeConfig | Mapping[str, Any],
        *,
        completion_func: Callable[..., Any] | None = None,
        openai_client_factory: Callable[..., Any] | None = None,
        anthropic_client_factory: Callable[..., Any] | None = None,
    ):
        self.config = config if isinstance(config, AIRuntimeConfig) else AIRuntimeConfig.from_mapping(config)
        self._litellm_adapter = LiteLLMChatAdapter(completion_func=completion_func)
        self._openai_adapter = OpenAIChatAdapter(client_factory=openai_client_factory)
        self._anthropic_adapter = AnthropicChatAdapter(client_factory=anthropic_client_factory)

    def resolve_runtime(self) -> ResolvedChatRuntime:
        return self.config.resolve_runtime()

    def runtime_summary(self) -> str:
        return runtime_summary(self.resolve_runtime().__dict__)

    def validate_config(self, *, require_api_key: bool = True) -> tuple[bool, str]:
        """Return validation status in the legacy tuple format."""

        try:
            self.config.validate(require_api_key=require_api_key)
        except AIConfigError as exc:
            return False, str(exc)
        return True, ""

    def build_completion_params(
        self,
        messages: Iterable[dict[str, Any]],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Expose normalized request building for wrappers and diagnostics."""

        return self.config.build_completion_params(messages, **overrides)

    def chat(self, messages: list[dict[str, Any]], **overrides: Any) -> str:
        """Call the configured model and normalize the returned content."""

        require_api_key = overrides.pop("require_api_key", True)
        params = self.build_completion_params(messages, **overrides)
        try:
            runtime = ResolvedChatRuntime(**validate_chat_runtime(params, require_api_key=require_api_key))
        except AIConfigError:
            raise

        request = ChatRequest(
            model=runtime.request_model,
            messages=list(params.get("messages", [])),
            temperature=float(params.get("temperature", runtime.temperature) or runtime.temperature),
            max_tokens=int(params.get("max_tokens", runtime.max_tokens) or runtime.max_tokens),
            timeout=int(params.get("timeout", runtime.timeout) or runtime.timeout),
            num_retries=int(params.get("num_retries", runtime.num_retries) or runtime.num_retries),
            api_key=str(params.get("api_key", runtime.api_key) or ""),
            api_base=str(params.get("api_base", runtime.api_base) or ""),
            driver=str(params.get("driver", runtime.driver) or runtime.driver),
            fallbacks=tuple(str(item) for item in params.get("fallbacks", runtime.fallback_models) or ()),
            extra_params=_extract_request_extras(params),
        )

        try:
            response = self._resolve_adapter(runtime.driver).chat(runtime, request)
        except Exception as exc:
            raise AIInvocationError(
                "AI completion request failed",
                details={"model": runtime.model, "driver": runtime.driver},
            ) from exc

        content = response.text
        if content is None:
            raise AIInvocationError(
                "AI completion response does not contain message content",
                details={"model": runtime.model, "driver": runtime.driver},
            )
        return coerce_text_content(content)

    def _resolve_adapter(self, driver: str) -> Any:
        if driver == "litellm":
            return self._litellm_adapter
        if driver == "openai":
            return self._openai_adapter
        if driver == "anthropic":
            return self._anthropic_adapter
        raise AIConfigError("Unsupported AI driver", details={"driver": driver})


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
        openai_client_factory: Callable[..., Any] | None = None,
        anthropic_client_factory: Callable[..., Any] | None = None,
    ):
        if isinstance(client, AIRuntimeClient):
            self._client = client
        else:
            self._client = AIRuntimeClient(
                client,
                completion_func=completion_func,
                openai_client_factory=openai_client_factory,
                anthropic_client_factory=anthropic_client_factory,
            )
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
        messages: Iterable[dict[str, Any]],
        **overrides: Any,
    ) -> dict[str, Any]:
        return self._client.build_completion_params(messages, **overrides)

    def resolve_runtime(self) -> ResolvedChatRuntime:
        return self._client.resolve_runtime()

    def runtime_summary(self) -> str:
        return self._client.runtime_summary()

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

    def chat(self, messages: list[dict[str, Any]], **overrides: Any) -> str:
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
        messages: Iterable[dict[str, Any]],
        overrides: Mapping[str, Any],
        cache_context: Any,
    ) -> str:
        normalized_messages = [_normalize_message(message) for message in messages]
        params = self.build_completion_params(normalized_messages, **overrides)
        key_payload = {
            "model": str(params.get("model", "") or ""),
            "driver": str(params.get("driver", "") or ""),
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


def _extract_request_extras(params: Mapping[str, Any]) -> dict[str, Any]:
    reserved = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "timeout",
        "num_retries",
        "api_key",
        "api_base",
        "driver",
        "fallbacks",
    }
    return {str(key): value for key, value in params.items() if key not in reserved}


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
