# coding=utf-8
"""Anthropic SDK-backed chat adapter."""

from __future__ import annotations

from typing import Any, Callable, Iterable

import anthropic

from newspulse.workflow.shared.ai_runtime.contracts import ChatRequest, ChatResponse, ResolvedChatRuntime


class AnthropicChatAdapter:
    """Send chat requests through the Anthropic SDK."""

    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self._client_factory = client_factory or anthropic.Anthropic

    def chat(self, runtime: ResolvedChatRuntime, request: ChatRequest) -> ChatResponse:
        client = self._client_factory(
            api_key=request.api_key or runtime.api_key,
            base_url=request.api_base or runtime.api_base or None,
            timeout=request.timeout,
            max_retries=request.num_retries,
        )
        system_prompt, messages = _to_anthropic_messages(request.messages)
        params: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "timeout": request.timeout,
        }
        if system_prompt:
            params["system"] = system_prompt
        params.update(dict(request.extra_params))
        response = client.messages.create(**params)
        text = _extract_text_blocks(getattr(response, "content", []) or [])
        return ChatResponse(
            text=text,
            raw_text=text,
            finish_reason=str(getattr(response, "stop_reason", "") or ""),
            provider_message={"driver": runtime.driver, "model": runtime.model},
            diagnostics={"driver": runtime.driver, "api_style": runtime.api_style},
        )


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
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text") is not None:
                    converted.append({"type": "text", "text": str(item.get("text", ""))})
                elif item.get("text") is not None:
                    converted.append({"type": "text", "text": str(item.get("text", ""))})
            else:
                text = str(item or "").strip()
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
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _extract_text_blocks(blocks: Iterable[Any]) -> str:
    parts: list[str] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
            continue
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if text:
                parts.append(str(text))
    return "\n".join(parts)
