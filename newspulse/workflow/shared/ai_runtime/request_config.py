# coding=utf-8
"""Helpers for consistent AI request and cache configuration."""

from __future__ import annotations

from typing import Any, Mapping

from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate


def build_request_overrides(
    config: Mapping[str, Any] | None,
    *,
    prompt_template: PromptTemplate | None = None,
    operation: str = "",
    prompt_name: str = "",
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge runtime overrides and default cache context for one AI operation."""

    request_overrides = dict(overrides or {})
    runtime_config = dict(config or {})

    timeout = runtime_config.get("TIMEOUT")
    if timeout is not None and "timeout" not in request_overrides:
        request_overrides["timeout"] = int(timeout)

    num_retries = runtime_config.get("NUM_RETRIES")
    if num_retries is not None and "num_retries" not in request_overrides:
        request_overrides["num_retries"] = int(num_retries)

    extra_params = runtime_config.get("EXTRA_PARAMS", {})
    if isinstance(extra_params, Mapping):
        for key, value in extra_params.items():
            request_overrides.setdefault(str(key), value)

    if prompt_template is not None:
        prompt_context = prompt_template.build_cache_context(
            operation=operation,
            prompt_name=prompt_name,
        )
    else:
        prompt_context = {
            key: value
            for key, value in {
                "operation": str(operation).strip(),
                "prompt_name": str(prompt_name).strip(),
            }.items()
            if value
        }

    if prompt_context:
        existing_context = request_overrides.get("cache_context")
        if isinstance(existing_context, Mapping):
            merged_context = dict(prompt_context)
            for key, value in existing_context.items():
                merged_context[str(key)] = value
            request_overrides["cache_context"] = merged_context
        elif existing_context is None:
            request_overrides["cache_context"] = prompt_context
        else:
            request_overrides["cache_context"] = {
                "default_scope": prompt_context,
                "custom_scope": existing_context,
            }

    return request_overrides


def resolve_runtime_cache_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return normalized runtime cache config from either supported key."""

    runtime_config = dict(config or {})
    for key in ("RUNTIME_CACHE", "LLM_CACHE"):
        cache_config = runtime_config.get(key, {})
        if isinstance(cache_config, Mapping) and cache_config:
            return dict(cache_config)
    return {}
