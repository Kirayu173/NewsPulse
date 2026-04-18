# coding=utf-8
"""Reusable AI runtime primitives for workflow stages."""

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient, AIRuntimeConfig
from newspulse.workflow.shared.ai_runtime.codec import (
    coerce_text_content,
    decode_json_response,
    extract_json_block,
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

__all__ = [
    "AIConfigError",
    "AIInvocationError",
    "AIPromptError",
    "AIResponseDecodeError",
    "AIRuntimeClient",
    "AIRuntimeConfig",
    "AIRuntimeError",
    "PromptTemplate",
    "PromptTemplateNotFoundError",
    "coerce_text_content",
    "decode_json_response",
    "extract_json_block",
    "load_prompt_template",
]
