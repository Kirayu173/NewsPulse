# coding=utf-8
"""Embedding runtime helpers shared by workflow stages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from newspulse.workflow.shared.ai_runtime.contracts import EmbeddingRequest, ResolvedEmbeddingRuntime
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError
from newspulse.workflow.shared.ai_runtime.resolver import normalize_model, resolve_embedding_runtime, runtime_summary, validate_embedding_runtime
from newspulse.workflow.shared.ai_runtime.adapters.litellm_embedding import LiteLLMEmbeddingAdapter
from newspulse.workflow.shared.ai_runtime.adapters.openai_embedding import OpenAIEmbeddingAdapter


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    """Normalized runtime configuration for embedding requests."""

    model: str = ""
    api_key: str = ""
    api_base: str = ""
    driver: str = "auto"
    timeout: int = 120
    batch_size: int = 64
    extra_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "EmbeddingRuntimeConfig":
        """Create a normalized embedding config from a loose runtime mapping."""

        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] not in (None, ""):
                    return config[name]
            return default

        driver = str(
            pick(
                "DRIVER",
                "driver",
                default=os.environ.get("AI_EMBEDDING_DRIVER", os.environ.get("EMBEDDING_DRIVER", "auto")),
            )
            or "auto"
        )
        api_base = str(
            pick(
                "API_BASE",
                "api_base",
                default=os.environ.get(
                    "AI_EMBEDDING_API_BASE",
                    os.environ.get(
                        "AI_EMBEDDING_BASE_URL",
                        os.environ.get(
                            "EMBEDDING_BASE_URL",
                            os.environ.get(
                                "AI_API_BASE",
                                os.environ.get("AI_BASE_URL", os.environ.get("BASE_URL", os.environ.get("API_BASE", ""))),
                            ),
                        ),
                    ),
                ),
            )
            or ""
        )
        model = normalize_model(
            str(
                pick(
                    "MODEL",
                    "model",
                    "EMBEDDING_MODEL",
                    "embedding_model",
                    "EMB_MODEL",
                    "emb_model",
                    default=os.environ.get(
                        "AI_EMBEDDING_MODEL",
                        os.environ.get("EMBEDDING_MODEL", os.environ.get("EMB_MODEL", "")),
                    ),
                )
                or ""
            ),
            api_base=api_base,
            driver=driver,
        )
        return cls(
            model=model,
            api_key=str(
                pick(
                    "API_KEY",
                    "api_key",
                    default=os.environ.get(
                        "AI_EMBEDDING_API_KEY",
                        os.environ.get("EMBEDDING_API_KEY", os.environ.get("AI_API_KEY", os.environ.get("API_KEY", ""))),
                    ),
                )
                or ""
            ),
            api_base=api_base,
            driver=driver,
            timeout=int(pick("TIMEOUT", "timeout", default=120) or 120),
            batch_size=int(
                pick(
                    "BATCH_SIZE",
                    "batch_size",
                    "EMBEDDING_BATCH_SIZE",
                    "embedding_batch_size",
                    default=64,
                )
                or 64
            ),
            extra_params=dict(pick("EXTRA_PARAMS", "extra_params", default={}) or {}),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "MODEL": self.model,
            "API_KEY": self.api_key,
            "API_BASE": self.api_base,
            "DRIVER": self.driver,
            "TIMEOUT": self.timeout,
            "BATCH_SIZE": self.batch_size,
            "EXTRA_PARAMS": dict(self.extra_params),
        }

    def resolve_runtime(self) -> ResolvedEmbeddingRuntime:
        runtime = resolve_embedding_runtime(self.to_mapping())
        return ResolvedEmbeddingRuntime(**runtime)

    def validate(self, *, require_api_key: bool = True) -> None:
        """Validate embedding runtime configuration."""

        validate_embedding_runtime(self.to_mapping(), require_api_key=require_api_key)

    def build_embedding_params(
        self,
        inputs: Sequence[str],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Build the provider request payload for one embedding batch."""

        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "input": list(inputs),
            "timeout": overrides.get("timeout", self.timeout),
            "driver": overrides.get("driver", self.driver),
        }
        api_key = overrides.get("api_key", self.api_key)
        if api_key:
            params["api_key"] = api_key
        api_base = overrides.get("api_base", self.api_base)
        if api_base:
            params["api_base"] = api_base

        passthrough = dict(self.extra_params)
        passthrough.update(overrides.get("extra_params", {}))
        for key, value in passthrough.items():
            if key not in params and value is not None:
                params[key] = value
        return params


class EmbeddingRuntimeClient:
    """Unified embedding runtime wrapper around LiteLLM and OpenAI SDK."""

    def __init__(
        self,
        config: EmbeddingRuntimeConfig | Mapping[str, Any],
        *,
        embedding_func: Callable[..., Any] | None = None,
        openai_client_factory: Callable[..., Any] | None = None,
    ):
        self.config = (
            config
            if isinstance(config, EmbeddingRuntimeConfig)
            else EmbeddingRuntimeConfig.from_mapping(config)
        )
        self._litellm_adapter = LiteLLMEmbeddingAdapter(embedding_func=embedding_func)
        self._openai_adapter = OpenAIEmbeddingAdapter(client_factory=openai_client_factory)

    def resolve_runtime(self) -> ResolvedEmbeddingRuntime:
        return self.config.resolve_runtime()

    def runtime_summary(self) -> str:
        return runtime_summary(self.resolve_runtime().__dict__)

    def is_enabled(self) -> bool:
        """Return True when an embedding model is configured."""

        return self.resolve_runtime().enabled

    def embed_texts(self, texts: Iterable[str], **overrides: Any) -> list[list[float]]:
        """Return one embedding vector for each input text."""

        normalized_inputs = [str(text or "") for text in texts]
        if not normalized_inputs:
            return []

        require_api_key = overrides.pop("require_api_key", True)
        batch_size = max(1, int(overrides.pop("batch_size", self.config.batch_size) or self.config.batch_size))
        rows: list[list[float]] = []
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
                driver=str(params.get("driver", runtime.driver) or runtime.driver),
                extra_params=_extract_request_extras(params),
            )
            try:
                response = self._resolve_adapter(runtime.driver).embed(runtime, request)
            except Exception as exc:
                raise AIInvocationError(
                    "Embedding request failed",
                    details={
                        "model": runtime.model,
                        "driver": runtime.driver,
                        "batch_index": batch_index,
                        "batch_size": len(batch_inputs),
                    },
                ) from exc

            batch_rows = response.vectors
            if len(batch_rows) != len(batch_inputs):
                raise AIInvocationError(
                    "Embedding response count does not match input count",
                    details={
                        "expected": len(batch_inputs),
                        "received": len(batch_rows),
                        "batch_index": batch_index,
                    },
                )
            rows.extend(batch_rows)
        return rows

    def _resolve_adapter(self, driver: str) -> Any:
        if driver == "litellm":
            return self._litellm_adapter
        if driver == "openai":
            return self._openai_adapter
        raise AIConfigError("Unsupported embedding driver", details={"driver": driver})


def _extract_request_extras(params: Mapping[str, Any]) -> dict[str, Any]:
    reserved = {"model", "input", "timeout", "api_key", "api_base", "driver"}
    return {str(key): value for key, value in params.items() if key not in reserved}


def _chunked(values: Sequence[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), batch_size):
        yield list(values[start : start + batch_size])
