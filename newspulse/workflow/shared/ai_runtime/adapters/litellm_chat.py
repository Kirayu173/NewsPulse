# coding=utf-8
"""LiteLLM-backed chat adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content
from newspulse.workflow.shared.ai_runtime.contracts import ChatRequest, ChatResponse, ResolvedChatRuntime


class LiteLLMChatAdapter:
    """Send chat requests through LiteLLM."""

    def __init__(self, completion_func: Callable[..., Any] | None = None):
        if completion_func is None:
            from litellm import completion as completion_func
        self._completion = completion_func

    def chat(self, runtime: ResolvedChatRuntime, request: ChatRequest) -> ChatResponse:
        params = {
            "model": request.model,
            "messages": list(request.messages),
            "temperature": request.temperature,
            "timeout": request.timeout,
            "num_retries": request.num_retries,
            **dict(request.extra_params),
        }
        if request.api_key:
            params["api_key"] = request.api_key
        if request.api_base:
            params["api_base"] = request.api_base
        if request.max_tokens > 0:
            params["max_tokens"] = request.max_tokens
        if request.fallbacks:
            params["fallbacks"] = list(request.fallbacks)

        response = self._completion(**params)
        message = _first_choice_message(response)
        content = getattr(message, "content", None)
        if content is None:
            content = getattr(message, "reasoning_content", None)
        text = coerce_text_content(content)
        return ChatResponse(
            text=text,
            raw_text=text,
            finish_reason=str(getattr(_first_choice(response), "finish_reason", "") or ""),
            provider_message={
                "driver": runtime.driver,
                "model": runtime.model,
            },
            diagnostics={"driver": runtime.driver, "api_style": runtime.api_style},
        )


def _first_choice(response: Any) -> Any:
    choices = getattr(response, "choices", None)
    if not choices:
        return SimpleNamespace(message=SimpleNamespace(content=None), finish_reason="")
    return choices[0]


def _first_choice_message(response: Any) -> Any:
    choice = _first_choice(response)
    return getattr(choice, "message", SimpleNamespace(content=None))
