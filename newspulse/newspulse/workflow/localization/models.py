# coding=utf-8
"""Private models used by the localization stage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalizationTextEntry:
    """A single text fragment that can be localized by the stage."""

    key: str
    text: str
    kind: str
