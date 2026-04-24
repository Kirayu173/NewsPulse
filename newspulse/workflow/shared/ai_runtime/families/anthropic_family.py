# coding=utf-8
"""Anthropic-family runtime implemented with the Anthropic SDK."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

import anthropic

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content, decode_json_response
from newspulse.workflow.shared.ai_runtime.contracts import ChatRequest, ResolvedChatRuntime
from newspulse.workflow.shared.ai_runtime.results import AIBlock, AIResult, AIUsage

_ANTHROPIC_ALLOWED_CHAT_KEYS = {
    "extra_body",
    "extra_headers",
    "extra_query",
    "metadata",
    "service_tier",
    "stop_sequences",
    "stream",
    "thinking",
    "tool_choice",
    "tools",
    "top_k",
    "top_p",
}


class AnthropicFamilyRuntime:
    """Run Anthropic-compatible chat requests via the Anthropic SDK."""

    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self._client_factory = client_factory or anthropic.Anthropic

    def generate(self, runtime: ResolvedChatRuntime, request: ChatRequest) -> AIResult:
        client = self._client_factory(
            api_key=_optional_str(request.api_key or runtime.api_key),
            base_url=_optional_str(request.api_base or runtime.api_base),
            timeout=request.timeout,
            max_retries=request.num_retries,
        )
        system_prompt, messages = _to_anthropic_messages(request.messages)
        params = _build_chat_params(request)
        params["messages"] = messages
        if system_prompt:
            params["system"] = system_prompt
        response = client.messages.create(**params)
        blocks = tuple(_normalize_blocks(getattr(response, "content", []) or []))
        text_blocks = tuple(block for block in blocks if block.type == "text")
        thinking_blocks = tuple(block for block in blocks if block.type in {"thinking", "redacted_thinking"})
        tool_calls = tuple(block.payload for block in blocks if block.type == "tool_use")
        text = "\n".join(
            str(block.payload.get("text", "") or "")
            for block in text_blocks
            if str(block.payload.get("text", "") or "").strip()
        )
        payload = decode_json_response(text) if request.response_mode == "json" else None
        continuation_payload = {
            "role": "assistant",
            "content": [
                {"type": block.type, **dict(block.payload)}
                for block in blocks
            ],
        }
        return AIResult(
            provider_family="anthropic",
            model=runtime.model,
            text=text,
            json_payload=payload,
            blocks=blocks,
            thinking_blocks=thinking_blocks,
            tool_calls=tool_calls,
            finish_reason=str(getattr(response, "stop_reason", "") or ""),
            usage=_anthropic_usage(getattr(response, "usage", None)),
            provider_response=response,
            continuation_payload=continuation_payload,
            diagnostics={
                "provider_family": "anthropic",
                "api_style": runtime.api_style,
                "response_mode": request.response_mode,
            },
        )


def _build_chat_params(request: ChatRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": request.model,
        "messages": list(request.messages),
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "timeout": request.timeout,
    }
    extras = _copy_mapping(request.extra_params)
    _merge_transport_overrides(params, extras)

    extra_body = _pop_mapping(extras, "extra_body")
    extras.pop("do_sample", None)
    if "thinking" not in extras and "thinking" in extra_body:
        extras["thinking"] = extra_body.pop("thinking")
    for key in sorted(list(extras)):
        if key in _ANTHROPIC_ALLOWED_CHAT_KEYS:
            params[key] = extras.pop(key)
    if extra_body:
        params["extra_body"] = extra_body
    return params


def _to_anthropic_messages(messages: Iterable[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user") or "user").strip().lower() or "user"
        content = message.get("content", "")
        if role == "system":
            text = _coerce_content_to_text(content)
            if text:
                system_parts.append(text)
            continue
        converted.append({"role": role, "content": _to_anthropic_content(content)})
    return "\n\n".join(part for part in system_parts if part), converted


def _to_anthropic_content(content: Any) -> Any:
    if isinstance(content, list):
        converted: list[dict[str, Any]] = []
        for item in content:
            payload = _to_mapping(item)
            block_type = str(payload.get("type", "") or "").strip()
            if block_type in {"tool_result", "tool_use", "thinking", "redacted_thinking"}:
                converted.append(payload)
            elif block_type == "text" and payload.get("text") is not None:
                converted.append({"type": "text", "text": str(payload.get("text", ""))})
            else:
                text = coerce_text_content(item)
                if text:
                    converted.append({"type": "text", "text": text})
        return converted or [{"type": "text", "text": ""}]
    return [{"type": "text", "text": _coerce_content_to_text(content)}]


def _coerce_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _to_mapping(item).get("text")
            if text is not None:
                parts.append(str(text))
            else:
                parts.append(coerce_text_content(item))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _normalize_blocks(blocks: Iterable[Any]) -> Iterable[AIBlock]:
    for block in blocks:
        payload = _to_mapping(block)
        block_type = str(payload.get("type", getattr(block, "type", "")) or "text").strip() or "text"
        if block_type == "text":
            payload.setdefault("text", coerce_text_content(block))
        elif block_type == "thinking":
            thinking = payload.get("thinking", getattr(block, "thinking", None))
            if thinking is not None:
                payload["thinking"] = thinking
        elif block_type == "redacted_thinking":
            payload.setdefault("data", payload.get("data", getattr(block, "data", None)))
        elif block_type == "tool_use":
            payload.setdefault("id", payload.get("id", getattr(block, "id", None)))
            payload.setdefault("name", payload.get("name", getattr(block, "name", None)))
            payload.setdefault("input", payload.get("input", getattr(block, "input", None)))
        yield AIBlock(type=block_type, payload=payload)


def _anthropic_usage(usage: Any) -> AIUsage | None:
    if usage is None:
        return None
    payload = _to_mapping(usage)
    input_tokens = int(payload.get("input_tokens", 0) or 0)
    output_tokens = int(payload.get("output_tokens", 0) or 0)
    total_tokens = int(payload.get("total_tokens", input_tokens + output_tokens) or 0)
    extra = {
        key: value
        for key, value in payload.items()
        if key not in {"input_tokens", "output_tokens", "total_tokens"}
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
