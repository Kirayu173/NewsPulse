# coding=utf-8
"""Shared helpers for resolving crawler source display names."""

from __future__ import annotations

from newspulse.crawler.sources import resolve_source_definition


def is_placeholder_source_name(name: str) -> bool:
    """Return True when a configured source name is visibly corrupted."""

    stripped = (name or "").strip()
    return bool(stripped) and set(stripped) == {"?"}


def resolve_source_display_name(source_id: str, requested_name: str = "") -> str:
    """Resolve a stable display name for one source."""

    stripped = (requested_name or "").strip()
    if stripped and not is_placeholder_source_name(stripped):
        return stripped

    try:
        definition = resolve_source_definition(source_id)
    except KeyError:
        return stripped or source_id

    fallback = (definition.default_name or "").strip()
    return fallback or stripped or source_id
