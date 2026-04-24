# coding=utf-8
"""Config normalization and provider-family runtime resolution helpers."""

from __future__ import annotations

from typing import Any, Mapping

from newspulse.workflow.shared.ai_runtime.errors import AIConfigError
from newspulse.workflow.shared.ai_runtime.provider_env import resolve_chat_env_defaults, resolve_embedding_env_defaults

_CHAT_PROVIDER_FAMILIES = {"auto", "openai", "anthropic"}
_EMBEDDING_PROVIDER_FAMILIES = {"openai"}


def detect_api_style(api_base: str) -> str:
    """Best-effort detection of protocol style from a base URL."""

    normalized = str(api_base or "").strip().lower()
    if not normalized:
        return ""
    if normalized.rstrip("/").endswith("/anthropic") or "/anthropic/" in normalized:
        return "anthropic"
    return "openai"


def normalize_model(model: str, api_base: str = "", provider_family: str = "auto") -> str:
    """Normalize plain model names into provider-family-prefixed forms when possible."""

    normalized = str(model or "").strip()
    if not normalized:
        return ""
    if "/" in normalized:
        return normalized

    normalized_family = _normalize_provider_family(provider_family, _CHAT_PROVIDER_FAMILIES)
    api_style = detect_api_style(api_base)
    if normalized_family == "anthropic" or api_style == "anthropic":
        return f"anthropic/{normalized}"
    return f"openai/{normalized}"


def resolve_chat_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve one loose chat config mapping into a concrete provider-family runtime."""

    normalized = _coerce_chat_mapping(config)
    api_style = detect_api_style(normalized["API_BASE"])
    provider_family = _resolve_chat_provider_family(
        normalized["PROVIDER_FAMILY"],
        normalized["MODEL"],
        api_style,
    )
    model = normalize_model(
        normalized["MODEL"],
        api_base=normalized["API_BASE"],
        provider_family=provider_family,
    )
    request_model = _request_model_for_family(model, provider_family)
    return {
        "provider_family": provider_family,
        "model": model,
        "request_model": request_model,
        "api_key": normalized["API_KEY"],
        "api_base": normalized["API_BASE"],
        "api_style": api_style or provider_family,
        "timeout": normalized["TIMEOUT"],
        "temperature": normalized["TEMPERATURE"],
        "max_tokens": normalized["MAX_TOKENS"],
        "num_retries": normalized["NUM_RETRIES"],
        "extra_params": dict(normalized["EXTRA_PARAMS"]),
        "capabilities": {
            "text": True,
            "json": True,
            "usage": True,
            "finish_reason": True,
            "provider_response": True,
            "native_blocks": provider_family == "anthropic",
            "tool_continuity": provider_family == "anthropic",
        },
    }


def resolve_embedding_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve one loose embedding config mapping into the OpenAI embedding runtime."""

    normalized = _coerce_embedding_mapping(config)
    model = normalize_model(
        normalized["MODEL"],
        api_base=normalized["API_BASE"],
        provider_family="openai",
    )
    request_model = _request_model_for_family(model, "openai")
    api_style = detect_api_style(normalized["API_BASE"])
    return {
        "provider_family": "openai",
        "model": model,
        "request_model": request_model,
        "api_key": normalized["API_KEY"],
        "api_base": normalized["API_BASE"],
        "api_style": api_style or "openai",
        "timeout": normalized["TIMEOUT"],
        "batch_size": normalized["BATCH_SIZE"],
        "enabled": bool(model),
        "extra_params": dict(normalized["EXTRA_PARAMS"]),
        "capabilities": {"embedding": True},
    }


def runtime_summary(runtime: Mapping[str, Any]) -> str:
    """Render a compact human-readable summary for diagnostics."""

    parts = [
        f"provider_family={runtime.get('provider_family', '')}",
        f"model={runtime.get('model', '')}",
    ]
    api_style = str(runtime.get("api_style", "") or "").strip()
    if api_style:
        parts.append(f"api_style={api_style}")
    api_base = str(runtime.get("api_base", "") or "").strip()
    if api_base:
        parts.append(f"api_base={api_base}")
    if "enabled" in runtime:
        parts.append(f"enabled={bool(runtime.get('enabled', False))}")
    return ", ".join(parts)


def validate_chat_runtime(config: Mapping[str, Any], *, require_api_key: bool = True) -> dict[str, Any]:
    """Validate one chat runtime mapping and return the resolved runtime."""

    runtime = resolve_chat_runtime(config)
    if not runtime["model"]:
        raise AIConfigError("AI model is not configured")
    if require_api_key and not runtime["api_key"]:
        raise AIConfigError("AI API key is not configured")
    if runtime["provider_family"] not in {"openai", "anthropic"}:
        raise AIConfigError(
            "Unsupported AI provider family",
            details={"provider_family": runtime["provider_family"]},
        )
    if runtime["provider_family"] == "anthropic":
        temperature_value = runtime.get("temperature", 1.0)
        temperature = 1.0 if temperature_value is None else float(temperature_value)
        if not (0.0 < temperature <= 1.0):
            raise AIConfigError(
                "Anthropic-compatible temperature must be within (0.0, 1.0]",
                details={"temperature": temperature, "model": runtime["model"]},
            )
    if runtime["provider_family"] == "openai" and _is_minimax_api_base(runtime.get("api_base", "")):
        temperature_value = runtime.get("temperature", 1.0)
        temperature = 1.0 if temperature_value is None else float(temperature_value)
        if not (0.0 < temperature <= 1.0):
            raise AIConfigError(
                "MiniMax OpenAI-compatible temperature must be within (0.0, 1.0]",
                details={"temperature": temperature, "model": runtime["model"]},
            )
    return runtime


def validate_embedding_runtime(config: Mapping[str, Any], *, require_api_key: bool = True) -> dict[str, Any]:
    """Validate one embedding runtime mapping and return the resolved runtime."""

    runtime = resolve_embedding_runtime(config)
    if not runtime["model"]:
        raise AIConfigError("Embedding model is not configured")
    if require_api_key and not runtime["api_key"]:
        raise AIConfigError("Embedding API key is not configured")
    if runtime["provider_family"] != "openai":
        raise AIConfigError(
            "Unsupported embedding provider family",
            details={"provider_family": runtime["provider_family"]},
        )
    return runtime


def _coerce_chat_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    model = str(_pick(config, "MODEL", "model", default="") or "").strip()
    api_key = str(_pick(config, "API_KEY", "api_key", default="") or "").strip()
    api_base = str(_pick(config, "API_BASE", "api_base", default="") or "").strip()
    provider_family = _normalize_provider_family(
        _pick(config, "PROVIDER_FAMILY", "provider_family", default="auto"),
        _CHAT_PROVIDER_FAMILIES,
    )

    env_defaults = resolve_chat_env_defaults(provider_family=provider_family, api_base=api_base, model=model)
    if not model:
        model = str(env_defaults.get("MODEL", "") or "").strip()
    if not api_base:
        api_base = str(env_defaults.get("API_BASE", "") or "").strip()
    if not api_key:
        api_key = str(env_defaults.get("API_KEY", "") or "").strip()
    if provider_family == "auto":
        env_family = str(env_defaults.get("PROVIDER_FAMILY", "") or "").strip().lower()
        if env_family in _CHAT_PROVIDER_FAMILIES:
            provider_family = env_family

    return {
        "MODEL": model,
        "API_KEY": api_key,
        "API_BASE": api_base,
        "PROVIDER_FAMILY": provider_family,
        "TIMEOUT": int(_pick(config, "TIMEOUT", "timeout", default=120) or 120),
        "TEMPERATURE": _coerce_float(_pick(config, "TEMPERATURE", "temperature", default=1.0), default=1.0),
        "MAX_TOKENS": int(_pick(config, "MAX_TOKENS", "max_tokens", default=5000) or 5000),
        "NUM_RETRIES": int(_pick(config, "NUM_RETRIES", "num_retries", default=2) or 2),
        "EXTRA_PARAMS": dict(_pick(config, "EXTRA_PARAMS", "extra_params", default={}) or {}),
    }


def _coerce_embedding_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    model = str(_pick(config, "MODEL", "model", default="") or "").strip()
    api_key = str(_pick(config, "API_KEY", "api_key", default="") or "").strip()
    api_base = str(_pick(config, "API_BASE", "api_base", default="") or "").strip()
    provider_family = str(
        _pick(config, "PROVIDER_FAMILY", "provider_family", default="openai") or "openai"
    ).strip().lower() or "openai"

    env_defaults = resolve_embedding_env_defaults(provider_family=provider_family, api_base=api_base, model=model)
    if not model:
        model = str(env_defaults.get("MODEL", "") or "").strip()
    if not api_base:
        api_base = str(env_defaults.get("API_BASE", "") or "").strip()
    if not api_key:
        api_key = str(env_defaults.get("API_KEY", "") or "").strip()

    return {
        "MODEL": model,
        "API_KEY": api_key,
        "API_BASE": api_base,
        "PROVIDER_FAMILY": "openai",
        "TIMEOUT": int(_pick(config, "TIMEOUT", "timeout", default=120) or 120),
        "BATCH_SIZE": int(_pick(config, "BATCH_SIZE", "batch_size", default=64) or 64),
        "EXTRA_PARAMS": dict(_pick(config, "EXTRA_PARAMS", "extra_params", default={}) or {}),
    }


def _resolve_chat_provider_family(provider_family: str, model: str, api_style: str) -> str:
    normalized_family = _normalize_provider_family(provider_family, _CHAT_PROVIDER_FAMILIES)
    if normalized_family != "auto":
        return normalized_family
    if api_style == "anthropic":
        return "anthropic"
    if _model_prefix(model) == "anthropic":
        return "anthropic"
    return "openai"


def _request_model_for_family(model: str, provider_family: str) -> str:
    if not model:
        return ""
    if "/" not in model:
        return model
    prefix, value = model.split("/", 1)
    if prefix.strip().lower() == provider_family:
        return value
    return model


def _model_prefix(model: str) -> str:
    if "/" not in str(model or ""):
        return ""
    return str(model).split("/", 1)[0].strip().lower()


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _pick(config: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in config and config[name] is not None:
            return config[name]
    return default


def _is_minimax_api_base(api_base: Any) -> bool:
    normalized = str(api_base or "").strip().lower()
    return "minimaxi.com" in normalized


def _normalize_provider_family(value: Any, allowed: set[str]) -> str:
    normalized = str(value or "auto").strip().lower() or "auto"
    if normalized not in allowed:
        raise AIConfigError("Unsupported AI provider family", details={"provider_family": normalized})
    return normalized
