# coding=utf-8
"""Environment fallback helpers for provider-family SDK runtime configs."""

from __future__ import annotations

import os
from typing import Any

_PROVIDER_ENV_KEYS = {
    "openai": {
        "api_key": ("OPENAI_API_KEY",),
        "api_base": ("OPENAI_BASE_URL",),
    },
    "anthropic": {
        "api_key": ("ANTHROPIC_API_KEY",),
        "api_base": ("ANTHROPIC_BASE_URL",),
    },
}


def resolve_chat_env_defaults(provider_family: Any = "", api_base: Any = "", model: Any = "") -> dict[str, str]:
    """Return unified chat runtime defaults from project and provider env vars."""

    family_hint = resolve_provider_family_hint(provider_family=provider_family, api_base=api_base, model=model)
    resolved_api_base = _first_nonempty_env("AI_API_BASE", "AI_BASE_URL", "API_BASE", "BASE_URL")
    if not resolved_api_base:
        resolved_api_base = _provider_env_value("api_base", family_hint)
    if not resolved_api_base and not family_hint:
        resolved_api_base = _unique_provider_env_value("api_base")

    resolved_provider_family = _first_nonempty_env("AI_PROVIDER_FAMILY", "PROVIDER_FAMILY")
    if not resolved_provider_family:
        resolved_provider_family = family_hint or resolve_provider_family_hint(api_base=resolved_api_base, model=model)

    resolved_api_key = _first_nonempty_env("AI_API_KEY", "API_KEY")
    key_hint = resolve_provider_family_hint(
        provider_family=resolved_provider_family,
        api_base=resolved_api_base,
        model=model,
    )
    if not resolved_api_key:
        resolved_api_key = _provider_env_value("api_key", key_hint)
    if not resolved_api_key and not key_hint:
        resolved_api_key = _unique_provider_env_value("api_key")

    return {
        "MODEL": _first_nonempty_env("AI_MODEL", "MODEL"),
        "API_KEY": resolved_api_key,
        "API_BASE": resolved_api_base,
        "PROVIDER_FAMILY": resolved_provider_family,
    }


def resolve_embedding_env_defaults(provider_family: Any = "", api_base: Any = "", model: Any = "") -> dict[str, str]:
    """Return embedding runtime defaults from embedding-specific env vars."""

    family_hint = resolve_provider_family_hint(provider_family=provider_family, api_base=api_base, model=model)
    if family_hint and family_hint != "openai":
        family_hint = "openai"

    resolved_api_base = _first_nonempty_env("AI_EMBEDDING_API_BASE", "AI_EMBEDDING_BASE_URL")
    if not resolved_api_base:
        resolved_api_base = _provider_env_value("api_base", "openai")

    resolved_provider_family = _first_nonempty_env("AI_EMBEDDING_PROVIDER_FAMILY") or "openai"

    resolved_api_key = _first_nonempty_env("AI_EMBEDDING_API_KEY")
    if not resolved_api_key:
        resolved_api_key = _provider_env_value("api_key", "openai")

    return {
        "MODEL": _first_nonempty_env("AI_EMBEDDING_MODEL", "EMB_MODEL"),
        "API_KEY": resolved_api_key,
        "API_BASE": resolved_api_base,
        "PROVIDER_FAMILY": resolved_provider_family,
    }


def resolve_provider_family_hint(provider_family: Any = "", api_base: Any = "", model: Any = "") -> str:
    """Return the provider family implied by the configured hint or endpoint."""

    normalized_family = str(provider_family or "").strip().lower()
    if normalized_family in {"openai", "anthropic"}:
        return normalized_family
    api_style = _detect_api_style(api_base)
    if api_style:
        return api_style
    return _model_prefix(model)


def _detect_api_style(api_base: Any) -> str:
    normalized = str(api_base or "").strip().lower()
    if not normalized:
        return ""
    if normalized.rstrip("/").endswith("/anthropic") or "/anthropic/" in normalized:
        return "anthropic"
    return "openai"


def _first_nonempty_env(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _provider_env_value(kind: str, provider_family: str) -> str:
    env_keys = _PROVIDER_ENV_KEYS.get(provider_family, {}).get(kind, ())
    return _first_nonempty_env(*env_keys)


def _unique_provider_env_value(kind: str, provider_families: tuple[str, ...] = ("openai", "anthropic")) -> str:
    values = []
    for provider_family in provider_families:
        value = _provider_env_value(kind, provider_family)
        if value:
            values.append(value)
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) == 1:
        return unique_values[0]
    return ""


def _model_prefix(model: Any) -> str:
    normalized = str(model or "").strip().lower()
    if "/" not in normalized:
        return ""
    prefix = normalized.split("/", 1)[0]
    if prefix in {"openai", "anthropic"}:
        return prefix
    return ""
