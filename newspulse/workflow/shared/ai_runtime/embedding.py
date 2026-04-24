# coding=utf-8
"""Compatibility exports for the provider-native embedding facade."""

from newspulse.workflow.shared.ai_runtime.config import EmbeddingRuntimeConfig
from newspulse.workflow.shared.ai_runtime.facade import EmbeddingRuntimeClient

__all__ = ["EmbeddingRuntimeClient", "EmbeddingRuntimeConfig"]
