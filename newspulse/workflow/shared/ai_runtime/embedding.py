# coding=utf-8
"""Embedding runtime helpers shared by workflow stages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeConfig
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    """Normalized runtime configuration for embedding requests."""

    model: str = ""
    api_key: str = ""
    api_base: str = ""
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

        api_base = str(pick("API_BASE", "api_base", default="") or "")
        model = AIRuntimeConfig.normalize_model(
            str(
                pick(
                    "MODEL",
                    "model",
                    "EMBEDDING_MODEL",
                    "embedding_model",
                    "EMB_MODEL",
                    "emb_model",
                    default=os.environ.get("EMB_MODEL", ""),
                )
                or ""
            ),
            api_base,
        )
        return cls(
            model=model,
            api_key=str(pick("API_KEY", "api_key", default=os.environ.get("AI_API_KEY", "")) or ""),
            api_base=api_base,
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

    def validate(self, *, require_api_key: bool = True) -> None:
        """Validate embedding runtime configuration."""

        if not self.model:
            raise AIConfigError("Embedding model is not configured")
        if require_api_key and not self.api_key:
            raise AIConfigError("Embedding API key is not configured")

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
    """Thin wrapper around an OpenAI-compatible embedding endpoint."""

    def __init__(
        self,
        config: EmbeddingRuntimeConfig | Mapping[str, Any],
        *,
        embedding_func: Callable[..., Any] | None = None,
    ):
        self.config = (
            config
            if isinstance(config, EmbeddingRuntimeConfig)
            else EmbeddingRuntimeConfig.from_mapping(config)
        )
        if embedding_func is None:
            from litellm import embedding as embedding_func

        self._embedding = embedding_func

    def is_enabled(self) -> bool:
        """Return True when an embedding model is configured."""

        return bool(self.config.model)

    def embed_texts(self, texts: Iterable[str], **overrides: Any) -> list[list[float]]:
        """Return one embedding vector for each input text."""

        normalized_inputs = [str(text or "") for text in texts]
        if not normalized_inputs:
            return []

        self.config.validate(require_api_key=overrides.pop("require_api_key", True))
        batch_size = max(1, int(overrides.pop("batch_size", self.config.batch_size) or self.config.batch_size))

        rows: list[list[float]] = []
        for batch_index, batch_inputs in enumerate(_chunked(normalized_inputs, batch_size), start=1):
            params = self.config.build_embedding_params(batch_inputs, **overrides)
            try:
                response = self._embedding(**params)
            except Exception as exc:
                raise AIInvocationError(
                    "Embedding request failed",
                    details={
                        "model": params.get("model", ""),
                        "batch_index": batch_index,
                        "batch_size": len(batch_inputs),
                    },
                ) from exc

            batch_rows = _coerce_embedding_rows(response)
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


def _coerce_embedding_rows(response: Any) -> list[list[float]]:
    if isinstance(response, Mapping):
        raw_rows = response.get("data", [])
    else:
        raw_rows = getattr(response, "data", [])

    rows: list[tuple[int, list[float]]] = []
    for fallback_index, entry in enumerate(raw_rows):
        if isinstance(entry, Mapping):
            vector = entry.get("embedding", [])
            index = int(entry.get("index", fallback_index))
        else:
            vector = getattr(entry, "embedding", [])
            index = int(getattr(entry, "index", fallback_index))
        rows.append((index, [float(value) for value in vector]))

    rows.sort(key=lambda item: item[0])
    return [vector for _, vector in rows]


def _chunked(values: Sequence[str], batch_size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), batch_size):
        yield list(values[start : start + batch_size])
