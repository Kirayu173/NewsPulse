# coding=utf-8
"""Shared selection context rendering helpers."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from newspulse.workflow.shared.contracts import HotlistItem


@dataclass(frozen=True)
class SelectionContext:
    """Compact, reusable context rendered from one hotlist item."""

    headline: str
    summary: str
    source_line: str
    attributes: tuple[str, ...] = ()
    embedding_text: str = ""
    llm_text: str = ""


def build_selection_context(item: HotlistItem) -> SelectionContext:
    """Build a shared selection context for semantic recall, LLM prompts, and review."""

    headline = str(item.title or "").strip()
    source_line = str(item.source_name or item.source_id or "").strip()
    summary = _resolve_summary(item)
    attributes = tuple(_build_attribute_lines(item))

    embedding_parts = [headline]
    if summary:
        embedding_parts.append(summary)
    if source_line:
        embedding_parts.append(f"source: {source_line}")
    embedding_parts.extend(attributes)

    llm_parts = []
    if summary:
        llm_parts.append(f"summary: {summary}")
    if source_line:
        llm_parts.append(f"source: {source_line}")
    llm_parts.extend(attributes)

    return SelectionContext(
        headline=headline,
        summary=summary,
        source_line=source_line,
        attributes=attributes,
        embedding_text="\n".join(part for part in embedding_parts if part),
        llm_text="\n".join(part for part in llm_parts if part),
    )


def _resolve_summary(item: HotlistItem) -> str:
    summary = str(item.summary or "").strip()
    if summary:
        return summary

    github = _github_payload(item.metadata)
    return str(github.get("description") or "").strip()


def _build_attribute_lines(item: HotlistItem) -> list[str]:
    source_kind = str(item.metadata.get("source_kind") or "").strip()
    if source_kind == "github_repository":
        return _build_github_attribute_lines(item)
    return []


def _build_github_attribute_lines(item: HotlistItem) -> list[str]:
    github = _github_payload(item.metadata)
    attributes: list[str] = []

    language = str(github.get("language") or "").strip()
    if language:
        attributes.append(f"language: {language}")

    topics = _normalize_topics(github.get("topics"))
    if topics:
        attributes.append(f"topics: {', '.join(topics[:5])}")

    stars_today = _coerce_int(github.get("stars_today"))
    if stars_today is not None:
        attributes.append(f"stars_today: {_format_number(stars_today)}")

    stars_total = _coerce_int(github.get("stars_total"))
    if stars_total is not None:
        attributes.append(f"stars_total: {_format_number(stars_total)}")

    forks_total = _coerce_int(github.get("forks_total"))
    if forks_total is not None:
        attributes.append(f"forks_total: {_format_number(forks_total)}")

    pushed_at = _short_iso_date(github.get("pushed_at"))
    if pushed_at:
        attributes.append(f"updated: {pushed_at}")

    created_at = _short_iso_date(github.get("created_at"))
    if created_at:
        attributes.append(f"created: {created_at}")

    flags = []
    if bool(github.get("archived")):
        flags.append("archived")
    if bool(github.get("fork")):
        flags.append("fork")
    if flags:
        attributes.append(f"repo_flags: {', '.join(flags)}")

    variant = str(github.get("source_variant") or "").strip()
    if variant:
        attributes.append(f"source_variant: {variant}")

    return attributes


def _github_payload(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    github = metadata.get("github")
    return dict(github) if isinstance(github, dict) else {}


def _normalize_topics(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [segment.strip() for segment in value.split(",")]
        return [part for part in parts if part]
    if not isinstance(value, Iterable):
        return []
    topics: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            topics.append(text)
    return topics


def _coerce_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: int) -> str:
    return f"{int(value):,}"


def _short_iso_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]
