# coding=utf-8
"""Insight stage package."""

from newspulse.workflow.insight.ai import AIInsightStrategy
from newspulse.workflow.insight.models import (
    DEFAULT_SECTION_TEMPLATES,
    InsightPromptPayload,
    InsightSectionTemplate,
    build_summary,
)
from newspulse.workflow.insight.noop import NoopInsightStrategy
from newspulse.workflow.insight.service import InsightService

__all__ = [
    "AIInsightStrategy",
    "DEFAULT_SECTION_TEMPLATES",
    "InsightPromptPayload",
    "InsightSectionTemplate",
    "InsightService",
    "NoopInsightStrategy",
    "build_summary",
]
