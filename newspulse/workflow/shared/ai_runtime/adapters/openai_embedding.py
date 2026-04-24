# coding=utf-8
"""OpenAI SDK-backed embedding adapter."""

from __future__ import annotations

from typing import Any, Callable

from openai import OpenAI

from newspulse.workflow.shared.ai_runtime.contracts import EmbeddingRequest, EmbeddingResponse, ResolvedEmbeddingRuntime


class OpenAIEmbeddingAdapter:
    """Send embedding requests through the OpenAI SDK."""

    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self._client_factory = client_factory or OpenAI

    def embed(self, runtime: ResolvedEmbeddingRuntime, request: EmbeddingRequest) -> EmbeddingResponse:
        client = self._client_factory(
            api_key=request.api_key or runtime.api_key,
            base_url=request.api_base or runtime.api_base or None,
            timeout=request.timeout,
            max_retries=2,
        )
        params: dict[str, Any] = {
            "model": request.model,
            "input": list(request.inputs),
            "timeout": request.timeout,
        }
        params.update(dict(request.extra_params))
        response = client.embeddings.create(**params)
        rows = [[float(value) for value in row.embedding] for row in response.data]
        return EmbeddingResponse(
            vectors=rows,
            diagnostics={"driver": runtime.driver, "api_style": runtime.api_style},
        )
