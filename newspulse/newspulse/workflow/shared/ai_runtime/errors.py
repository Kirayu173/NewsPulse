# coding=utf-8
"""Typed error objects used by the shared AI runtime."""

from __future__ import annotations

from typing import Any, Dict, Optional


class AIRuntimeError(Exception):
    """Base exception for the shared workflow AI runtime."""

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if not self.details:
            return self.message
        details = ", ".join(f"{key}={value}" for key, value in sorted(self.details.items()))
        return f"{self.message} ({details})"


class AIConfigError(AIRuntimeError):
    """Raised when the AI runtime configuration is incomplete or invalid."""


class AIPromptError(AIRuntimeError):
    """Raised when loading or parsing prompts fails."""


class PromptTemplateNotFoundError(AIPromptError):
    """Raised when a required prompt template file is missing."""


class AIInvocationError(AIRuntimeError):
    """Raised when the underlying LLM call fails."""


class AIResponseDecodeError(AIRuntimeError):
    """Raised when the AI response cannot be decoded into structured data."""

