# coding=utf-8
"""Compatibility exports for the provider-native AI chat facade."""

from newspulse.workflow.shared.ai_runtime.config import AIRuntimeConfig
from newspulse.workflow.shared.ai_runtime.facade import AIRuntimeClient, CachedAIRuntimeClient

__all__ = ["AIRuntimeClient", "AIRuntimeConfig", "CachedAIRuntimeClient"]
