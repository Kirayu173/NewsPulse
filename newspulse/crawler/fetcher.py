# coding=utf-8
"""Builtin hotlist fetcher."""

from __future__ import annotations

import random
import time
from typing import Optional

from newspulse.crawler.models import (
    CrawlBatchResult,
    CrawlSourceSpec,
    SourceFetchFailure,
    SourceFetchResult,
)
from newspulse.crawler.source_names import resolve_source_display_name
from newspulse.crawler.sources import SourceClient, resolve_source_definition


class DataFetcher:
    """Fetch hotlist data from builtin Python sources."""

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        # `api_url` is kept only for constructor compatibility.
        self.proxy_url = proxy_url
        self.api_url = api_url or "builtin"
        self.client = SourceClient(proxy_url=proxy_url)

    def fetch_source(
        self,
        source_spec: CrawlSourceSpec,
        *,
        max_retries: int = 2,
        min_retry_wait: int = 3,
        max_retry_wait: int = 5,
    ) -> SourceFetchResult | SourceFetchFailure:
        """Fetch one source with retries and structured failure details."""

        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                definition = resolve_source_definition(source_spec.source_id)
                source_name = resolve_source_display_name(
                    source_spec.source_id,
                    source_spec.source_name,
                )
                items = definition.handler(self.client)
                print(f"获取 {source_spec.source_id} 成功（builtin，本地实现）")
                return SourceFetchResult(
                    source_id=source_spec.source_id,
                    source_name=source_name,
                    resolved_source_id=definition.canonical_id,
                    items=list(items),
                    attempts=attempts,
                    metadata={"category": definition.category},
                )
            except Exception as exc:
                if attempts <= max_retries:
                    base_wait = random.uniform(min_retry_wait, max_retry_wait)
                    additional_wait = (attempts - 1) * random.uniform(1, 2)
                    wait_time = base_wait + additional_wait
                    print(f"请求 {source_spec.source_id} 失败: {exc}. {wait_time:.2f}秒后重试...")
                    time.sleep(wait_time)
                    continue

                print(f"请求 {source_spec.source_id} 失败: {exc}")
                resolved_source_id = source_spec.source_id
                category = ""
                try:
                    definition = resolve_source_definition(source_spec.source_id)
                    resolved_source_id = definition.canonical_id
                    category = definition.category
                    source_name = resolve_source_display_name(
                        source_spec.source_id,
                        source_spec.source_name,
                    )
                except KeyError:
                    source_name = resolve_source_display_name(
                        source_spec.source_id,
                        source_spec.source_name,
                    )

                return SourceFetchFailure(
                    source_id=source_spec.source_id,
                    source_name=source_name,
                    resolved_source_id=resolved_source_id,
                    exception_type=exc.__class__.__name__,
                    message=str(exc),
                    attempts=attempts,
                    retryable=max_retries > 0,
                    metadata={"category": category},
                )

        return SourceFetchFailure(
            source_id=source_spec.source_id,
            source_name=resolve_source_display_name(
                source_spec.source_id,
                source_spec.source_name,
            ),
            resolved_source_id=source_spec.source_id,
            exception_type="RuntimeError",
            message="unknown fetch failure",
            attempts=attempts,
            retryable=max_retries > 0,
            metadata={},
        )

    def crawl(
        self,
        source_specs: list[CrawlSourceSpec],
        request_interval: int = 100,
    ) -> CrawlBatchResult:
        """Fetch multiple hotlist sources and return the native batch contract."""

        sources: list[SourceFetchResult] = []
        failures: list[SourceFetchFailure] = []

        for index, source_spec in enumerate(source_specs):
            result = self.fetch_source(source_spec)
            if isinstance(result, SourceFetchFailure):
                failures.append(result)
            else:
                sources.append(result)

            if index < len(source_specs) - 1:
                actual_interval = request_interval + random.randint(-10, 20)
                actual_interval = max(50, actual_interval)
                time.sleep(actual_interval / 1000)

        print(f"成功: {[source.source_id for source in sources]}, 失败: {[failure.source_id for failure in failures]}")
        return CrawlBatchResult(
            sources=sources,
            failures=failures,
            metadata={"requested_source_count": len(source_specs)},
        )
