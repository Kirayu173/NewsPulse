# coding=utf-8
"""Builtin hotlist sources."""

from newspulse.crawler.sources.base import SourceClient, SourceItem
from newspulse.crawler.sources.registry import SOURCE_REGISTRY, get_source_handler

__all__ = ["SourceClient", "SourceItem", "SOURCE_REGISTRY", "get_source_handler"]
