# coding=utf-8
"""LiteLLM-backed embedding adapter."""

from __future__ import annotations

from typing import Any, Callable

from newspulse.workflow.shared.ai_runtime.contracts import EmbeddingRequest, EmbeddingResponse, ResolvedEmbeddingRuntime


class LiteLLMEmbeddingAdapter:
    """Send embedding requests through LiteLLM."""

    def __init__(self, embedding_func: Callable[..., Any] | None = None):
        if embedding_func is None:
            from litellm import embedding as embedding_func
        self._embedding = embedding_func

    def embed(self, runtime: ResolvedEmbeddingRuntime, request: EmbeddingRequest) -> EmbeddingResponse:
        params = {
            "model": request.model,
            "input": list(request.inputs),
            "timeout": request.timeout,
            **dict(request.extra_params),
        }
        if request.api_key:
            params["api_key"] = request.api_key
        if request.api_base:
            params["api_base"] = request.api_base
        response = self._embedding(**params)
        return EmbeddingResponse(
            vectors=_coerce_embedding_rows(response),
            diagnostics={"driver": runtime.driver, "api_style": runtime.api_style},
        )


def _coerce_embedding_rows(response: Any) -> list[list[float]]:
    raw_rows = response.get("data", []) if isinstance(response, dict) else getattr(response, "data", [])
    rows: list[tuple[int, list[float]]] = []
    for fallback_index, entry in enumerate(raw_rows):
        if isinstance(entry, dict):
            vector = entry.get("embedding", [])
            index = int(entry.get("index", fallback_index))
        else:
            vector = getattr(entry, "embedding", [])
            index = int(getattr(entry, "index", fallback_index))
        rows.append((index, [float(value) for value in vector]))
    rows.sort(key=lambda item: item[0])
    return [vector for _, vector in rows]
