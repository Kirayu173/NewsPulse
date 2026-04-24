# coding=utf-8
"""Config normalization and runtime resolution helpers."""

from __future__ import annotations

from typing import Any, Mapping

from newspulse.workflow.shared.ai_runtime.errors import AIConfigError

_CHAT_DRIVERS = {"auto", "litellm", "openai", "anthropic"}
_EMBEDDING_DRIVERS = {"auto", "litellm", "openai"}


def detect_api_style(api_base: str) -> str:
    """Best-effort detection of protocol style from a base URL."""

    normalized = str(api_base or "").strip().lower()
    if not normalized:
        return ""
    if normalized.rstrip("/").endswith("/anthropic") or "/anthropic/" in normalized:
        return "anthropic"
    return "openai"


def normalize_model(model: str, api_base: str = "", driver: str = "auto") -> str:
    """Normalize plain model names into protocol-specific forms when possible."""

    normalized = str(model or "").strip()
    if not normalized:
        return ""
    if "/" in normalized:
        return normalized

    normalized_driver = _normalize_driver_name(driver, _CHAT_DRIVERS)
    api_style = detect_api_style(api_base)
    if normalized_driver == "anthropic" or api_style == "anthropic":
        return f"anthropic/{normalized}"
    if normalized_driver == "openai" or api_style == "openai":
        return f"openai/{normalized}"
    return normalized


def resolve_chat_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve one loose chat config mapping into a concrete backend choice."""

    normalized = _coerce_runtime_mapping(config)
    api_style = detect_api_style(normalized["API_BASE"])
    model = normalize_model(
        normalized["MODEL"],
        api_base=normalized["API_BASE"],
        driver=normalized["DRIVER"],
    )
    driver = _resolve_chat_driver(normalized["DRIVER"], model, api_style)
    request_model = _request_model_for_driver(model, driver)
    return {
        "driver": driver,
        "model": model,
        "request_model": request_model,
        "api_key": normalized["API_KEY"],
        "api_base": normalized["API_BASE"],
        "api_style": api_style,
        "timeout": normalized["TIMEOUT"],
        "temperature": normalized["TEMPERATURE"],
        "max_tokens": normalized["MAX_TOKENS"],
        "num_retries": normalized["NUM_RETRIES"],
        "fallback_models": tuple(str(item) for item in normalized["FALLBACK_MODELS"] if str(item).strip()),
        "extra_params": dict(normalized["EXTRA_PARAMS"]),
        "capabilities": {
            "text_input": True,
            "text_output": True,
            "embedding_supported": driver in {"litellm", "openai"},
        },
    }


def resolve_embedding_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve one loose embedding config mapping into a concrete backend choice."""

    normalized = _coerce_embedding_mapping(config)
    api_style = detect_api_style(normalized["API_BASE"])
    model = normalize_model(
        normalized["MODEL"],
        api_base=normalized["API_BASE"],
        driver=normalized["DRIVER"],
    )
    driver = _resolve_embedding_driver(normalized["DRIVER"], model, api_style)
    request_model = _request_model_for_driver(model, driver)
    return {
        "driver": driver,
        "model": model,
        "request_model": request_model,
        "api_key": normalized["API_KEY"],
        "api_base": normalized["API_BASE"],
        "api_style": api_style,
        "timeout": normalized["TIMEOUT"],
        "batch_size": normalized["BATCH_SIZE"],
        "enabled": bool(model),
        "extra_params": dict(normalized["EXTRA_PARAMS"]),
        "capabilities": {"embedding": True},
    }


def runtime_summary(runtime: Mapping[str, Any]) -> str:
    """Render a compact human-readable summary for diagnostics."""

    parts = [
        f"driver={runtime.get('driver', '')}",
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
    if runtime["driver"] not in {"litellm", "openai", "anthropic"}:
        raise AIConfigError("Unsupported AI driver", details={"driver": runtime["driver"]})
    if runtime["driver"] == "litellm" and "/" not in runtime["model"]:
        raise AIConfigError("AI model must use provider/model format", details={"model": runtime["model"]})
    return runtime


def validate_embedding_runtime(config: Mapping[str, Any], *, require_api_key: bool = True) -> dict[str, Any]:
    """Validate one embedding runtime mapping and return the resolved runtime."""

    runtime = resolve_embedding_runtime(config)
    if not runtime["model"]:
        raise AIConfigError("Embedding model is not configured")
    if require_api_key and not runtime["api_key"]:
        raise AIConfigError("Embedding API key is not configured")
    if runtime["driver"] not in {"litellm", "openai"}:
        raise AIConfigError("Unsupported embedding driver", details={"driver": runtime["driver"]})
    if runtime["driver"] == "litellm" and "/" not in runtime["model"]:
        raise AIConfigError("Embedding model must use provider/model format", details={"model": runtime["model"]})
    return runtime


def _coerce_runtime_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "MODEL": str(_pick(config, "MODEL", "model", default="") or "").strip(),
        "API_KEY": str(_pick(config, "API_KEY", "api_key", default="") or "").strip(),
        "API_BASE": str(_pick(config, "API_BASE", "api_base", default="") or "").strip(),
        "DRIVER": _normalize_driver_name(_pick(config, "DRIVER", "driver", default="auto"), _CHAT_DRIVERS),
        "TIMEOUT": int(_pick(config, "TIMEOUT", "timeout", default=120) or 120),
        "TEMPERATURE": float(_pick(config, "TEMPERATURE", "temperature", default=1.0) or 1.0),
        "MAX_TOKENS": int(_pick(config, "MAX_TOKENS", "max_tokens", default=5000) or 5000),
        "NUM_RETRIES": int(_pick(config, "NUM_RETRIES", "num_retries", default=2) or 2),
        "FALLBACK_MODELS": list(_pick(config, "FALLBACK_MODELS", "fallback_models", default=[]) or []),
        "EXTRA_PARAMS": dict(_pick(config, "EXTRA_PARAMS", "extra_params", default={}) or {}),
    }


def _coerce_embedding_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "MODEL": str(_pick(config, "MODEL", "model", default="") or "").strip(),
        "API_KEY": str(_pick(config, "API_KEY", "api_key", default="") or "").strip(),
        "API_BASE": str(_pick(config, "API_BASE", "api_base", default="") or "").strip(),
        "DRIVER": _normalize_driver_name(_pick(config, "DRIVER", "driver", default="auto"), _EMBEDDING_DRIVERS),
        "TIMEOUT": int(_pick(config, "TIMEOUT", "timeout", default=120) or 120),
        "BATCH_SIZE": int(_pick(config, "BATCH_SIZE", "batch_size", default=64) or 64),
        "EXTRA_PARAMS": dict(_pick(config, "EXTRA_PARAMS", "extra_params", default={}) or {}),
    }


def _resolve_chat_driver(driver: str, model: str, api_style: str) -> str:
    normalized_driver = _normalize_driver_name(driver, _CHAT_DRIVERS)
    if normalized_driver != "auto":
        return normalized_driver

    model_prefix = _model_prefix(model)
    if api_style == "anthropic":
        return "anthropic"
    if api_style == "openai":
        if model_prefix and model_prefix not in {"openai", "anthropic"}:
            return "litellm"
        return "openai"
    if model_prefix == "anthropic":
        return "anthropic"
    return "litellm"


def _resolve_embedding_driver(driver: str, model: str, api_style: str) -> str:
    normalized_driver = _normalize_driver_name(driver, _EMBEDDING_DRIVERS)
    if normalized_driver != "auto":
        return normalized_driver

    model_prefix = _model_prefix(model)
    if api_style == "openai":
        if model_prefix and model_prefix not in {"openai"}:
            return "litellm"
        return "openai"
    return "litellm"


def _request_model_for_driver(model: str, driver: str) -> str:
    if not model:
        return ""
    if driver in {"openai", "anthropic"} and "/" in model:
        return model.split("/", 1)[1]
    return model


def _model_prefix(model: str) -> str:
    if "/" not in str(model or ""):
        return ""
    return str(model).split("/", 1)[0].strip().lower()


def _pick(config: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in config and config[name] is not None:
            return config[name]
    return default


def _normalize_driver_name(value: Any, allowed: set[str]) -> str:
    normalized = str(value or "auto").strip().lower() or "auto"
    if normalized not in allowed:
        raise AIConfigError("Unsupported AI driver", details={"driver": normalized})
    return normalized
