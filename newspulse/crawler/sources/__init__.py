# coding=utf-8
"""Builtin hotlist sources."""

from newspulse.crawler.sources.base import SourceClient, SourceItem
from newspulse.crawler.sources.registry import (
    SOURCE_ALIAS_INDEX,
    SOURCE_DEFINITIONS,
    SOURCE_REGISTRY,
    get_source_handler,
    resolve_source_definition,
)

__all__ = [
    "SourceClient",
    "SourceItem",
    "SOURCE_ALIAS_INDEX",
    "SOURCE_DEFINITIONS",
    "SOURCE_REGISTRY",
    "get_source_handler",
    "resolve_source_definition",
]
