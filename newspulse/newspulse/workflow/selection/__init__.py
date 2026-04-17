# coding=utf-8
"""Selection stage package."""

from newspulse.workflow.selection.ai import AISelectionStrategy
from newspulse.workflow.selection.keyword import KeywordSelectionStrategy
from newspulse.workflow.selection.models import AIActiveTag, AIBatchNewsItem, AIClassificationResult, KeywordGroupDefinition
from newspulse.workflow.selection.service import SelectionService

__all__ = [
    "AIActiveTag",
    "AIBatchNewsItem",
    "AIClassificationResult",
    "AISelectionStrategy",
    "KeywordGroupDefinition",
    "KeywordSelectionStrategy",
    "SelectionService",
]
