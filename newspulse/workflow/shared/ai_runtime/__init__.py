# coding=utf-8
"""Reusable provider-native AI runtime primitives for workflow stages."""

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient, AIRuntimeConfig, CachedAIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import (
    coerce_text_content,
    decode_json_response,
    extract_json_block,
)
from newspulse.workflow.shared.ai_runtime.embedding import (
    EmbeddingRuntimeClient,
    EmbeddingRuntimeConfig,
)
from newspulse.workflow.shared.ai_runtime.errors import (
    AIConfigError,
    AIInvocationError,
    AIPromptError,
    AIResponseDecodeError,
    AIRuntimeError,
    PromptTemplateNotFoundError,
)
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import (
    build_request_overrides,
    resolve_runtime_cache_config,
)
from newspulse.workflow.shared.ai_runtime.results import AIBlock, AIResult, AIUsage, EmbeddingResult

__all__ = [
    "AIBlock",
    "AIConfigError",
    "AIInvocationError",
    "AIPromptError",
    "AIResponseDecodeError",
    "AIResult",
    "AIRuntimeClient",
    "AIRuntimeConfig",
    "CachedAIRuntimeClient",
    "AIRuntimeError",
    "AIUsage",
    "PromptTemplate",
    "PromptTemplateNotFoundError",
    "coerce_text_content",
    "decode_json_response",
    "EmbeddingResult",
    "EmbeddingRuntimeClient",
    "EmbeddingRuntimeConfig",
    "extract_json_block",
    "build_request_overrides",
    "load_prompt_template",
    "resolve_runtime_cache_config",
]
