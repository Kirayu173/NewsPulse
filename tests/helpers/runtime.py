from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from newspulse.runtime import RuntimeProviders, build_runtime
from newspulse.workflow.shared.ai_runtime.results import AIResult, EmbeddingResult


def build_runtime_with_storage(config: Mapping[str, Any], storage_manager):
    providers = RuntimeProviders(storage_factory=lambda settings: storage_manager)
    return build_runtime(config, providers=providers)


def json_result(payload: Any, *, provider_family: str = "openai", model: str = "openai/test-model") -> AIResult:
    return AIResult(
        provider_family=provider_family,
        model=model,
        text=json.dumps(payload, ensure_ascii=False),
        json_payload=payload,
    )


def text_result(text: str, *, provider_family: str = "openai", model: str = "openai/test-model") -> AIResult:
    return AIResult(
        provider_family=provider_family,
        model=model,
        text=str(text),
    )


def embedding_result(
    vectors: Sequence[Sequence[float]],
    *,
    provider_family: str = "openai",
    model: str = "openai/embedding-test",
) -> EmbeddingResult:
    return EmbeddingResult(
        provider_family=provider_family,
        model=model,
        vectors=tuple(tuple(float(value) for value in row) for row in vectors),
    )
