# coding=utf-8
"""Private models used by the insight stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InsightPromptPayload:
    """Rendered payload that will be sent to the insight model."""

    report_mode: str
    report_type: str
    current_time: str
    news_count: int
    platforms: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    news_content: str = ""
    standalone_content: str = ""
    language: str = "Chinese"


@dataclass(frozen=True)
class InsightSectionTemplate:
    """Definition used to normalize AI JSON fields into insight sections."""

    key: str
    title: str
    field_name: str
    summary_limit: int = 120


DEFAULT_SECTION_TEMPLATES = (
    InsightSectionTemplate(key="core_trends", title="Core Trends", field_name="core_trends"),
    InsightSectionTemplate(
        key="sentiment_controversy",
        title="Sentiment & Controversy",
        field_name="sentiment_controversy",
    ),
    InsightSectionTemplate(key="signals", title="Signals", field_name="signals"),
    InsightSectionTemplate(
        key="outlook_strategy",
        title="Outlook & Strategy",
        field_name="outlook_strategy",
    ),
)


def build_summary(content: str, limit: int = 120) -> str:
    """Create a short plain-text summary from a longer insight paragraph."""

    normalized = " ".join((content or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."
