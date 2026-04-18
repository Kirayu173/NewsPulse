# coding=utf-8
"""Compatibility exports for builtin hotlist source handlers."""

from newspulse.crawler.sources.finance import *  # noqa: F401,F403
from newspulse.crawler.sources.mainland import *  # noqa: F401,F403
from newspulse.crawler.sources.misc import *  # noqa: F401,F403
from newspulse.crawler.sources.registry import SOURCE_REGISTRY, get_source_handler
from newspulse.crawler.sources.tech import *  # noqa: F401,F403

__all__ = ["SOURCE_REGISTRY", "get_source_handler"]
