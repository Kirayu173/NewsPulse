# coding=utf-8
"""Private models used by the localization stage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocalizationTextEntry:
    """A single text fragment that can be localized by the stage."""

    key: str
    text: str
    kind: str


@dataclass(frozen=True)
class LocalizationTextResult:
    """The translation outcome for a single localized text fragment."""

    original_text: str = ""
    translated_text: str = ""
    success: bool = False
    error: str = ""


@dataclass(frozen=True)
class LocalizationBatchResult:
    """Structured batch translation result used by the localization stage."""

    results: list[LocalizationTextResult] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    total_count: int = 0
    prompt: str = ""
    raw_response: str = ""
    parsed_count: int = 0

    @classmethod
    def empty(cls, *, total_count: int = 0) -> "LocalizationBatchResult":
        """Return an empty batch result."""

        return cls(total_count=total_count)

    @classmethod
    def failed(cls, texts: list[str], error: str, *, prompt: str = "") -> "LocalizationBatchResult":
        """Return a failed batch result with one error result per input item."""

        return cls(
            results=[
                LocalizationTextResult(original_text=text, error=error)
                for text in texts
            ],
            success_count=0,
            fail_count=len(texts),
            total_count=len(texts),
            prompt=prompt,
        )
