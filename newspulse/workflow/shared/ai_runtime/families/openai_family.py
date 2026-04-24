# coding=utf-8
"""OpenAI-family runtime implemented with the OpenAI SDK."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from openai import OpenAI

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content, decode_json_response
from newspulse.workflow.shared.ai_runtime.contracts import (
    ChatRequest,
    EmbeddingRequest,
    ResolvedChatRuntime,
    ResolvedEmbeddingRuntime,
)
from newspulse.workflow.shared.ai_runtime.results import AIBlock, AIResult, AIUsage, EmbeddingResult

_OPENAI_ALLOWED_CHAT_KEYS = {
    "audio",
    "extra_body",
    "extra_headers",
    "extra_query",
    "frequency_penalty",
    "function_call",
    "functions",
    "logit_bias",
    "logprobs",
    "metadata",
    "modalities",
    "n",
    "parallel_tool_calls",
    "prediction",
    "presence_penalty",
    "prompt_cache_key",
    "prompt_cache_retention",
    "reasoning_effort",
    "response_format",
    "safety_identifier",
    "seed",
    "service_tier",
    "stop",
    "store",
    "stream",
    "stream_options",
    "tool_choice",
    "tools",
    "top_logprobs",
    "top_p",
    "user",
    "verbosity",
    "web_search_options",
}

_OPENAI_ALLOWED_EMBEDDING_KEYS = {
    "dimensions",
    "encoding_format",
    "extra_body",
    "extra_headers",
    "extra_query",
    "user",
}


class OpenAIFamilyRuntime:
    """Run OpenAI-compatible chat and embedding requests via the OpenAI SDK."""

    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self._client_factory = client_factory or OpenAI

    def generate(self, runtime: ResolvedChatRuntime, request: ChatRequest) -> AIResult:
        client = self._client_factory(
            api_key=_optional_str(request.api_key or runtime.api_key),
            base_url=_optional_str(request.api_base or runtime.api_base),
            timeout=request.timeout,
            max_retries=request.num_retries,
        )
        params = _build_chat_params(request)
        response = client.chat.completions.create(**params)
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        text = coerce_text_content(content)
        blocks = tuple(_content_blocks(content, text))
        tool_calls = tuple(_tool_calls(getattr(message, "tool_calls", None)))
        payload = decode_json_response(text) if request.response_mode == "json" else None
        return AIResult(
            provider_family="openai",
            model=runtime.model,
            text=text,
            json_payload=payload,
            blocks=blocks,
            tool_calls=tool_calls,
            finish_reason=str(getattr(choice, "finish_reason", "") or ""),
            usage=_openai_usage(getattr(response, "usage", None)),
            provider_response=response,
            diagnostics={
                "provider_family": "openai",
                "api_style": runtime.api_style,
                "response_mode": request.response_mode,
            },
        )

    def embed(self, runtime: ResolvedEmbeddingRuntime, request: EmbeddingRequest) -> EmbeddingResult:
        client = self._client_factory(
            api_key=_optional_str(request.api_key or runtime.api_key),
            base_url=_optional_str(request.api_base or runtime.api_base),
            timeout=request.timeout,
            max_retries=2,
        )
        params = _build_embedding_params(request)
        response = client.embeddings.create(**params)
        rows = tuple(tuple(float(value) for value in row.embedding) for row in response.data)
        return EmbeddingResult(
            provider_family="openai",
            model=runtime.model,
            vectors=rows,
            usage=_openai_usage(getattr(response, "usage", None)),
            provider_response=response,
            diagnostics={
                "provider_family": "openai",
                "api_style": runtime.api_style,
            },
        )


def _build_chat_params(request: ChatRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": request.model,
        "messages": list(request.messages),
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "timeout": request.timeout,
    }
    extras = _copy_mapping(request.extra_params)
    _merge_transport_overrides(params, extras)

    extra_body = _pop_mapping(extras, "extra_body")
    if request.response_mode == "json" and "response_format" not in extras and "response_format" not in extra_body:
        params["response_format"] = {"type": "json_object"}
    for key in sorted(list(extras)):
        if key in _OPENAI_ALLOWED_CHAT_KEYS:
            params[key] = extras.pop(key)
    if extra_body:
        params["extra_body"] = extra_body
    return params


def _build_embedding_params(request: EmbeddingRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": request.model,
        "input": list(request.inputs),
        "timeout": request.timeout,
    }
    extras = _copy_mapping(request.extra_params)
    _merge_transport_overrides(params, extras)

    extra_body = _pop_mapping(extras, "extra_body")
    for key in sorted(list(extras)):
        if key in _OPENAI_ALLOWED_EMBEDDING_KEYS:
            params[key] = extras.pop(key)
    if extra_body:
        params["extra_body"] = extra_body
    return params


def _content_blocks(content: Any, fallback_text: str) -> Iterable[AIBlock]:
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                block_type = str(item.get("type", "text") or "text")
                payload = dict(item)
            else:
                block_type = str(getattr(item, "type", "text") or "text")
                payload = _to_mapping(item)
                if block_type == "text" and "text" not in payload:
                    payload["text"] = coerce_text_content(item)
            yield AIBlock(type=block_type, payload=payload)
        return
    text = fallback_text or coerce_text_content(content)
    if text:
        yield AIBlock(type="text", payload={"text": text})


def _tool_calls(tool_calls: Any) -> Iterable[dict[str, Any]]:
    if not tool_calls:
        return ()
    normalized = []
    for tool_call in tool_calls:
        payload = _to_mapping(tool_call)
        function_payload = _to_mapping(payload.get("function", getattr(tool_call, "function", None)))
        if function_payload:
            payload["function"] = function_payload
        normalized.append(payload)
    return normalized


def _openai_usage(usage: Any) -> AIUsage | None:
    if usage is None:
        return None
    payload = _to_mapping(usage)
    input_tokens = int(payload.get("prompt_tokens", payload.get("input_tokens", 0)) or 0)
    output_tokens = int(payload.get("completion_tokens", payload.get("output_tokens", 0)) or 0)
    total_tokens = int(payload.get("total_tokens", input_tokens + output_tokens) or 0)
    extra = {
        key: value
        for key, value in payload.items()
        if key not in {"prompt_tokens", "input_tokens", "completion_tokens", "output_tokens", "total_tokens"}
    }
    return AIUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        extra=extra,
    )


def _merge_transport_overrides(params: dict[str, Any], extras: dict[str, Any]) -> None:
    for key in ("extra_headers", "extra_query"):
        value = extras.pop(key, None)
        if value is None:
            continue
        params[key] = dict(value) if isinstance(value, Mapping) else value


def _pop_mapping(extras: dict[str, Any], key: str) -> dict[str, Any]:
    value = extras.pop(key, None)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dict(dumped)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
