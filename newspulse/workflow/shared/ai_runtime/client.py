# coding=utf-8
"""Shared AI client used by workflow stages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from newspulse.workflow.shared.ai_runtime.codec import coerce_text_content
from newspulse.workflow.shared.ai_runtime.errors import AIConfigError, AIInvocationError


@dataclass(frozen=True)
class AIRuntimeConfig:
    """Normalized runtime configuration for LLM calls."""

    model: str = "deepseek/deepseek-chat"
    api_key: str = ""
    api_base: str = ""
    temperature: float = 1.0
    max_tokens: int = 5000
    timeout: int = 120
    num_retries: int = 2
    fallback_models: list[str] = field(default_factory=list)

    @staticmethod
    def normalize_model(model: str, api_base: str = "") -> str:
        """Allow plain model names when using an OpenAI-compatible base URL."""

        normalized = (model or "").strip()
        if not normalized:
            return ""
        if "/" in normalized:
            return normalized
        if api_base:
            return f"openai/{normalized}"
        return normalized

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any]) -> "AIRuntimeConfig":
        """Create a normalized runtime config from mixed-case config mappings."""

        def pick(*names: str, default: Any = None) -> Any:
            for name in names:
                if name in config and config[name] is not None:
                    return config[name]
            return default

        api_key = pick("API_KEY", "api_key", default=os.environ.get("AI_API_KEY", ""))
        api_base = pick("API_BASE", "api_base", default="")
        model = cls.normalize_model(
            pick("MODEL", "model", default="deepseek/deepseek-chat"),
            api_base,
        )
        fallback_models = list(pick("FALLBACK_MODELS", "fallback_models", default=[]))
        return cls(
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=float(pick("TEMPERATURE", "temperature", default=1.0)),
            max_tokens=int(pick("MAX_TOKENS", "max_tokens", default=5000)),
            timeout=int(pick("TIMEOUT", "timeout", default=120)),
            num_retries=int(pick("NUM_RETRIES", "num_retries", default=2)),
            fallback_models=fallback_models,
        )

    def validate(self, *, require_api_key: bool = True) -> None:
        """Validate the runtime configuration and raise typed errors on failure."""

        if not self.model:
            raise AIConfigError("AI model is not configured")
        if require_api_key and not self.api_key:
            raise AIConfigError("AI API key is not configured")
        if "/" not in self.model:
            raise AIConfigError(
                "AI model must use provider/model format",
                details={"model": self.model},
            )

    def build_completion_params(
        self,
        messages: Iterable[dict[str, str]],
        **overrides: Any,
    ) -> dict[str, Any]:
        """Build the LiteLLM completion payload for a chat request."""

        params: dict[str, Any] = {
            "model": overrides.get("model", self.model),
            "messages": list(messages),
            "temperature": overrides.get("temperature", self.temperature),
            "timeout": overrides.get("timeout", self.timeout),
            "num_retries": overrides.get("num_retries", self.num_retries),
        }

        api_key = overrides.get("api_key", self.api_key)
        if api_key:
            params["api_key"] = api_key

        api_base = overrides.get("api_base", self.api_base)
        if api_base:
            params["api_base"] = api_base

        max_tokens = overrides.get("max_tokens", self.max_tokens)
        if max_tokens and max_tokens > 0:
            params["max_tokens"] = max_tokens

        fallbacks = overrides.get("fallbacks", self.fallback_models)
        if fallbacks:
            params["fallbacks"] = list(fallbacks)

        passthrough_keys = set(params)
        for key, value in overrides.items():
            if key not in passthrough_keys:
                params[key] = value
        return params


class AIRuntimeClient:
    """Thin shared wrapper around LiteLLM chat completion."""

    def __init__(
        self,
        config: AIRuntimeConfig | Mapping[str, Any],
        *,
        completion_func: Callable[..., Any] | None = None,
    ):
        self.config = config if isinstance(config, AIRuntimeConfig) else AIRuntimeConfig.from_mapping(config)
        if completion_func is None:
            from litellm import completion as completion_func

        self._completion = completion_func

    def validate_config(self, *, require_api_key: bool = True) -> tuple[bool, str]:
        """Return validation status in the legacy tuple format."""

        try:
            self.config.validate(require_api_key=require_api_key)
        except AIConfigError as exc:
            return False, str(exc)
        return True, ""

    def chat(self, messages: list[dict[str, str]], **overrides: Any) -> str:
        """Call the configured model and normalize the returned content."""

        self.config.validate(require_api_key=overrides.pop("require_api_key", True))
        params = self.config.build_completion_params(messages, **overrides)

        try:
            response = self._completion(**params)
        except Exception as exc:
            raise AIInvocationError(
                "AI completion request failed",
                details={"model": params.get("model", "")},
            ) from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise AIInvocationError("AI completion response does not contain message content") from exc
        return coerce_text_content(content)
