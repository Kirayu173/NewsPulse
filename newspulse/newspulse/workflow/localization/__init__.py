# coding=utf-8
"""Localization stage package."""

from newspulse.workflow.localization.ai import AILocalizationStrategy
from newspulse.workflow.localization.models import (
    LocalizationBatchResult,
    LocalizationTextEntry,
    LocalizationTextResult,
)
from newspulse.workflow.localization.noop import NoopLocalizationStrategy
from newspulse.workflow.localization.service import LocalizationService

__all__ = [
    "AILocalizationStrategy",
    "LocalizationBatchResult",
    "LocalizationService",
    "LocalizationTextEntry",
    "LocalizationTextResult",
    "NoopLocalizationStrategy",
]
