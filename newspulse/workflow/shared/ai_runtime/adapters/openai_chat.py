# coding=utf-8
"""OpenAI SDK-backed chat adapter."""

from __future__ import annotations

from typing import Any, Callable

from openai import OpenAI

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content
from newspulse.workflow.shared.ai_runtime.contracts import ChatRequest, ChatResponse, ResolvedChatRuntime


class OpenAIChatAdapter:
    """Send chat requests through the OpenAI SDK."""

    def __init__(self, client_factory: Callable[..., Any] | None = None):
        self._client_factory = client_factory or OpenAI

    def chat(self, runtime: ResolvedChatRuntime, request: ChatRequest) -> ChatResponse:
        client = self._client_factory(
            api_key=request.api_key or runtime.api_key,
            base_url=request.api_base or runtime.api_base or None,
            timeout=request.timeout,
            max_retries=request.num_retries,
        )
        params: dict[str, Any] = {
            "model": request.model,
            "messages": list(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout,
        }
        params.update(dict(request.extra_params))
        response = client.chat.completions.create(**params)
        choice = response.choices[0]
        content = getattr(choice.message, "content", None)
        text = coerce_text_content(content)
        return ChatResponse(
            text=text,
            raw_text=text,
            finish_reason=str(getattr(choice, "finish_reason", "") or ""),
            provider_message={"driver": runtime.driver, "model": runtime.model},
            diagnostics={"driver": runtime.driver, "api_style": runtime.api_style},
        )
