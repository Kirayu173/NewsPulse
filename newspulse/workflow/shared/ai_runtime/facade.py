# coding=utf-8
"""Unified provider-native AI facade used by workflow stages."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from newspulse.workflow.shared.ai_runtime.config import AIRuntimeConfig, EmbeddingRuntimeConfig
from newspulse.workflow.shared.ai_runtime.contracts import (
    ChatRequest,
    EmbeddingRequest,
    ResolvedChatRuntime,
    ResolvedEmbeddingRuntime,
)
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError
from newspulse.workflow.shared.ai_runtime.families import AnthropicFamilyRuntime, OpenAIFamilyRuntime
from newspulse.workflow.shared.ai_runtime.resolver import runtime_summary, validate_chat_runtime, validate_embedding_runtime
from newspulse.workflow.shared.ai_runtime.results import AIResult, EmbeddingResult

_CACHE_EXCLUDED_PARAM_KEYS = {"api_key", "timeout", "num_retries", "require_api_key"}


class AIRuntimeClient:
    """Unified facade that preserves provider-native chat results."""

    def __init__(
        self,
        config: AIRuntimeConfig | Mapping[str, Any],
        *,
        openai_client_factory: Callable[..., Any] | None = None,
        anthropic_client_factory: Callable[..., Any] | None = None,
    ):
        self.config = config if isinstance(config, AIRuntimeConfig) else AIRuntimeConfig.from_mapping(config)
        self._openai_family = OpenAIFamilyRuntime(client_factory=openai_client_factory)
        self._anthropic_family = AnthropicFamilyRuntime(client_factory=anthropic_client_factory)

    def resolve_runtime(self) -> ResolvedChatRuntime:
        return self.config.resolve_runtime()

    def runtime_summary(self) -> str:
        return runtime_summary(self.resolve_runtime().__dict__)

    def build_completion_params(self, messages: Iterable[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
        return self.config.build_completion_params(messages, **overrides)

    def generate_text(self, messages: list[dict[str, Any]], **overrides: Any) -> AIResult:
        return self._invoke("text", messages, **overrides)

    def generate_json(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: Mapping[str, Any] | None = None,
        **overrides: Any,
    ) -> AIResult:
        return self._invoke("json", messages, json_schema=dict(schema) if isinstance(schema, Mapping) else None, **overrides)

    def generate_native(self, messages: list[dict[str, Any]], **overrides: Any) -> AIResult:
        return self._invoke("native", messages, **overrides)

    def _invoke(
        self,
        response_mode: str,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        **overrides: Any,
    ) -> AIResult:
        require_api_key = overrides.pop("require_api_key", True)
        params = self.build_completion_params(messages, **overrides)
        try:
            runtime = ResolvedChatRuntime(**validate_chat_runtime(params, require_api_key=require_api_key))
        except AIConfigError:
            raise

        request = ChatRequest(
            model=runtime.request_model,
            messages=list(params.get("messages", [])),
            response_mode=response_mode,
            json_schema=json_schema,
            temperature=float(params.get("temperature", runtime.temperature) or runtime.temperature),
            max_tokens=int(params.get("max_tokens", runtime.max_tokens) or runtime.max_tokens),
            timeout=int(params.get("timeout", runtime.timeout) or runtime.timeout),
            num_retries=int(params.get("num_retries", runtime.num_retries) or runtime.num_retries),
            api_key=str(params.get("api_key", runtime.api_key) or ""),
            api_base=str(params.get("api_base", runtime.api_base) or ""),
            extra_params=_extract_chat_extras(params),
        )
        try:
            return self._resolve_family(runtime.provider_family).generate(runtime, request)
        except Exception as exc:
            raise AIInvocationError(
                "AI completion request failed",
                details={
                    "model": runtime.model,
                    "provider_family": runtime.provider_family,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                },
            ) from exc

    def _resolve_family(self, provider_family: str) -> Any:
        if provider_family == "openai":
            return self._openai_family
        if provider_family == "anthropic":
            return self._anthropic_family
        raise AIConfigError(
            "Unsupported AI provider family",
            details={"provider_family": provider_family},
        )


class CachedAIRuntimeClient:
    """In-memory TTL cache wrapper for repeated AI runtime requests."""

    def __init__(
        self,
        client: AIRuntimeClient | AIRuntimeConfig | Mapping[str, Any],
        *,
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
                openai_client_factory=openai_client_factory,
                anthropic_client_factory=anthropic_client_factory,
            )
        self.enabled = bool(enabled)
        self.ttl_seconds = max(0, int(ttl_seconds or 0))
        self.max_entries = max(0, int(max_entries or 0))
        self._clock = clock or time.monotonic
        self._cache: dict[str, tuple[float, AIResult]] = {}
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._evictions = 0

    @property
    def config(self) -> AIRuntimeConfig:
        return self._client.config

    def build_completion_params(self, messages: Iterable[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
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

    def generate_text(self, messages: list[dict[str, Any]], **overrides: Any) -> AIResult:
        return self._generate_cached("text", messages, None, **overrides)

    def generate_json(self, messages: list[dict[str, Any]], *, schema: Mapping[str, Any] | None = None, **overrides: Any) -> AIResult:
        normalized_schema = dict(schema) if isinstance(schema, Mapping) else None
        return self._generate_cached("json", messages, normalized_schema, **overrides)

    def generate_native(self, messages: list[dict[str, Any]], **overrides: Any) -> AIResult:
        return self._generate_cached("native", messages, None, **overrides)

    def _generate_cached(
        self,
        response_mode: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        **overrides: Any,
    ) -> AIResult:
        cache_enabled = overrides.pop("cache_enabled", self.enabled)
        cache_bypass = bool(overrides.pop("cache_bypass", False))
        cache_context = overrides.pop("cache_context", None)
        ttl_override = overrides.pop("cache_ttl_seconds", None)
        ttl_seconds = self.ttl_seconds if ttl_override is None else max(0, int(ttl_override or 0))

        if not cache_enabled or cache_bypass or ttl_seconds <= 0 or self.max_entries <= 0:
            return self._dispatch(response_mode, messages, schema, **overrides)

        now = self._clock()
        self._purge_expired(now)
        cache_key = self._build_cache_key(messages, overrides, cache_context, response_mode, schema)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > now:
            self._hits += 1
            return cached[1]

        self._misses += 1
        response = self._dispatch(response_mode, messages, schema, **overrides)
        self._store(cache_key, response, ttl_seconds, now)
        return response

    def _dispatch(
        self,
        response_mode: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        **overrides: Any,
    ) -> AIResult:
        if response_mode == "text":
            return self._client.generate_text(messages, **overrides)
        if response_mode == "json":
            return self._client.generate_json(messages, schema=schema, **overrides)
        return self._client.generate_native(messages, **overrides)

    def _store(self, cache_key: str, response: AIResult, ttl_seconds: int, now: float) -> None:
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
        response_mode: str,
        schema: dict[str, Any] | None,
    ) -> str:
        normalized_messages = [_normalize_message(message) for message in messages]
        params = self.build_completion_params(normalized_messages, **overrides)
        key_payload = {
            "response_mode": response_mode,
            "schema": _normalize_cache_value(schema),
            "model": str(params.get("model", "") or ""),
            "provider_family": str(params.get("provider_family", "") or ""),
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


class EmbeddingRuntimeClient:
    """OpenAI-compatible embedding facade used by the semantic recall layer."""

    def __init__(
        self,
        config: EmbeddingRuntimeConfig | Mapping[str, Any],
        *,
        openai_client_factory: Callable[..., Any] | None = None,
    ):
        self.config = config if isinstance(config, EmbeddingRuntimeConfig) else EmbeddingRuntimeConfig.from_mapping(config)
        self._openai_family = OpenAIFamilyRuntime(client_factory=openai_client_factory)

    def resolve_runtime(self) -> ResolvedEmbeddingRuntime:
        return self.config.resolve_runtime()

    def runtime_summary(self) -> str:
        return runtime_summary(self.resolve_runtime().__dict__)

    def is_enabled(self) -> bool:
        return self.resolve_runtime().enabled

    def generate_embeddings(self, texts: Iterable[str], **overrides: Any) -> EmbeddingResult:
        normalized_inputs = [str(text or "") for text in texts]
        if not normalized_inputs:
            return EmbeddingResult(provider_family="openai", model=self.config.model, vectors=())

        require_api_key = overrides.pop("require_api_key", True)
        batch_size = max(1, int(overrides.pop("batch_size", self.config.batch_size) or self.config.batch_size))
        rows: list[tuple[float, ...]] = []
        usage = None
        last_response = None
        runtime = None
        for batch_index, batch_inputs in enumerate(_chunked(normalized_inputs, batch_size), start=1):
            params = self.config.build_embedding_params(batch_inputs, **overrides)
            try:
                runtime = ResolvedEmbeddingRuntime(**validate_embedding_runtime(params, require_api_key=require_api_key))
            except AIConfigError:
                raise

            request = EmbeddingRequest(
                model=runtime.request_model,
                inputs=list(batch_inputs),
                timeout=int(params.get("timeout", runtime.timeout) or runtime.timeout),
                batch_size=batch_size,
                api_key=str(params.get("api_key", runtime.api_key) or ""),
                api_base=str(params.get("api_base", runtime.api_base) or ""),
                extra_params=_extract_embedding_extras(params),
            )
            try:
                result = self._openai_family.embed(runtime, request)
            except Exception as exc:
                raise AIInvocationError(
                    "Embedding request failed",
                    details={
                        "model": runtime.model,
                        "provider_family": runtime.provider_family,
                        "batch_index": batch_index,
                        "batch_size": len(batch_inputs),
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    },
                ) from exc

            if len(result.vectors) != len(batch_inputs):
                raise AIInvocationError(
                    "Embedding response count does not match input count",
                    details={
                        "expected": len(batch_inputs),
                        "received": len(result.vectors),
                        "batch_index": batch_index,
                    },
                )
            rows.extend(result.vectors)
            usage = result.usage
            last_response = result.provider_response

        resolved_model = runtime.model if runtime is not None else self.config.model
        return EmbeddingResult(
            provider_family="openai",
            model=resolved_model,
            vectors=tuple(rows),
            usage=usage,
            provider_response=last_response,
            diagnostics={
                "provider_family": "openai",
                "batch_size": batch_size,
            },
        )

    def embed_texts(self, texts: Iterable[str], **overrides: Any) -> EmbeddingResult:
        return self.generate_embeddings(texts, **overrides)


def _extract_chat_extras(params: Mapping[str, Any]) -> dict[str, Any]:
    reserved = {
        "model",
        "messages",
        "temperature",
        "max_tokens",
        "timeout",
        "num_retries",
        "api_key",
        "api_base",
        "provider_family",
    }
    return {str(key): value for key, value in params.items() if key not in reserved}


def _extract_embedding_extras(params: Mapping[str, Any]) -> dict[str, Any]:
    reserved = {"model", "input", "timeout", "api_key", "api_base", "provider_family"}
    return {str(key): value for key, value in params.items() if key not in reserved}


def _normalize_message(message: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in sorted(message.items(), key=lambda item: str(item[0])):
        normalized[str(key)] = _normalize_cache_value(value)
    return normalized


def _normalize_cache_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_cache_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize_cache_value(item) for item in value]
    if hasattr(value, "json_payload"):
        return {
            "provider_family": getattr(value, "provider_family", ""),
            "model": getattr(value, "model", ""),
            "text": getattr(value, "text", ""),
            "json_payload": _normalize_cache_value(getattr(value, "json_payload", None)),
        }
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _normalize_cache_value(vars(value))
    return value


def _chunked(values: Sequence[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), batch_size):
        yield list(values[start : start + batch_size])
