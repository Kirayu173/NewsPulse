# coding=utf-8
"""Structured crawler input and output models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from newspulse.crawler.sources.base import SourceClient, SourceItem


SourceHandler = Callable[["SourceClient"], list["SourceItem"]]


@dataclass(frozen=True)
class CrawlSourceSpec:
    """Requested source spec for one crawl run."""

    source_id: str
    source_name: str = ""


@dataclass(frozen=True)
class SourceDefinition:
    """Registered source metadata and handler."""

    canonical_id: str
    handler: SourceHandler
    default_name: str = ""
    category: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceFetchResult:
    """Successful fetch result for one source."""

    source_id: str
    source_name: str
    resolved_source_id: str
    items: list["SourceItem"] = field(default_factory=list)
    attempts: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceFetchFailure:
    """Structured failure details for one source."""

    source_id: str
    source_name: str
    resolved_source_id: str
    exception_type: str
    message: str
    attempts: int = 1
    retryable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlBatchResult:
    """Batch crawl output consumed by downstream normalization/storage."""

    sources: list[SourceFetchResult] = field(default_factory=list)
    failures: list[SourceFetchFailure] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def platform_names(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for source in self.sources:
            names[source.source_id] = source.source_name or source.source_id
        for failure in self.failures:
            names[failure.source_id] = failure.source_name or failure.source_id
        return names

    @property
    def successful_source_ids(self) -> list[str]:
        return [source.source_id for source in self.sources]

    @property
    def failed_source_ids(self) -> list[str]:
        return [failure.source_id for failure in self.failures]
