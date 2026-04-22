# coding=utf-8
"""Async network fetcher for the insight content stage."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import aiohttp

from newspulse.crawler.sources.base import DEFAULT_HEADERS, strip_html
from newspulse.utils.url import normalize_url
from newspulse.workflow.insight.content_fetcher import (
    _extract_hn_external_url,
    _extract_hn_item_text,
    _first_line,
    _format_repo_stats,
    _hash_text,
    _is_meaningful_text,
    _trim_text,
)
from newspulse.workflow.insight.models import InsightContentPayload, InsightNewsContext

if TYPE_CHECKING:
    from newspulse.workflow.insight.content_fetcher import InsightContentFetcher


class AsyncInsightContentFetcher:
    def __init__(
        self,
        fetcher: "InsightContentFetcher",
        *,
        concurrency: int,
        request_timeout: int,
    ) -> None:
        self.fetcher = fetcher
        self.concurrency = max(2, int(concurrency or 2))
        self.request_timeout = max(3, int(request_timeout or fetcher.timeout))

    async def fetch_many(self, contexts: list[InsightNewsContext]) -> list[InsightContentPayload]:
        if not contexts:
            return []

        connector = aiohttp.TCPConnector(
            limit=self.concurrency,
            limit_per_host=max(2, min(self.concurrency, 8)),
        )
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        semaphore = asyncio.Semaphore(self.concurrency)

        async with aiohttp.ClientSession(
            headers=dict(DEFAULT_HEADERS),
            connector=connector,
            timeout=timeout,
            trust_env=True,
        ) as session:
            tasks = [
                asyncio.create_task(self._fetch_one(session, semaphore, context))
                for context in contexts
            ]
            return list(await asyncio.gather(*tasks))

    async def _fetch_one(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        context: InsightNewsContext,
    ) -> InsightContentPayload:
        async with semaphore:
            source_kind = str(context.source_context.source_kind or "").strip()
            if source_kind == "github_repository":
                return await self._fetch_github_context(session, context)
            if source_kind == "hackernews_item":
                return await self._fetch_hackernews_context(session, context)
            return await self._fetch_article_context(session, context)

    async def _fetch_article_context(
        self,
        session: aiohttp.ClientSession,
        context: InsightNewsContext,
        *,
        override_url: str | None = None,
        source_type: str = "article",
    ) -> InsightContentPayload:
        target_url = str(override_url or context.url or context.mobile_url or "").strip()
        if not target_url:
            return self.fetcher._fallback_summary_payload(
                context,
                source_type=source_type,
                error_type="missing_url",
                error_message="content route does not have a usable URL",
            )

        normalized_url = normalize_url(target_url, context.source_id)
        cached = self.fetcher._load_cached(normalized_url, context.news_item_id)
        if cached is not None:
            return cached

        try:
            html, final_url, status_code = await self._request_text(session, target_url)
        except Exception as exc:
            return self.fetcher._fallback_summary_payload(
                context,
                source_type=source_type,
                normalized_url=normalized_url,
                final_url=target_url,
                error_type="request_failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        attempts: list[dict[str, Any]] = []
        for extractor in self.fetcher.extractors:
            extracted = extractor.extract(url=final_url, html=html)
            attempts.append(
                {
                    "extractor": extractor.name,
                    "success": extracted.success,
                    "error_type": extracted.error_type,
                    "error_message": extracted.error_message,
                    "text_length": len(extracted.text or ""),
                }
            )
            if extracted.success and _is_meaningful_text(extracted.text):
                payload = InsightContentPayload(
                    news_item_id=context.news_item_id,
                    status="ok",
                    source_type=source_type,
                    normalized_url=normalized_url,
                    final_url=extracted.final_url or final_url,
                    title=extracted.title or context.title,
                    excerpt=extracted.excerpt,
                    content_text=extracted.text,
                    content_markdown=extracted.markdown or extracted.text,
                    published_at=extracted.published_at,
                    author=extracted.author,
                    extractor_name=extracted.extractor_name,
                    content_hash=_hash_text(extracted.text),
                    trace={
                        "cache_hit": False,
                        "http_status": status_code,
                        "attempts": attempts,
                    },
                )
                self.fetcher._save_payload(context, payload)
                return payload

        last_attempt = attempts[-1] if attempts else {}
        return self.fetcher._fallback_summary_payload(
            context,
            source_type=source_type,
            normalized_url=normalized_url,
            final_url=final_url,
            error_type=str(last_attempt.get("error_type", "extract_failed") or "extract_failed"),
            error_message=str(last_attempt.get("error_message", "all extractors returned empty content") or ""),
            trace={"cache_hit": False, "attempts": attempts},
        )

    async def _fetch_github_context(
        self,
        session: aiohttp.ClientSession,
        context: InsightNewsContext,
    ) -> InsightContentPayload:
        repo = dict(context.source_context.metadata or {})
        full_name = str(repo.get("full_name") or context.title or "").strip()
        repo_url = str(context.url or (f"https://github.com/{full_name}" if full_name else "")).strip()
        normalized_url = normalize_url(repo_url, context.source_id)
        cached = self.fetcher._load_cached(normalized_url, context.news_item_id)
        if cached is not None:
            return cached

        readme_task = asyncio.create_task(self._fetch_github_readme(session, full_name))
        release_task = asyncio.create_task(self._fetch_github_latest_release(session, full_name))
        readme_text, readme_trace = await readme_task
        release_text, release_trace = await release_task

        blocks: list[str] = []
        if full_name:
            blocks.append(f"Repository: {full_name}")
        description = str(repo.get("description") or context.source_context.summary or "").strip()
        if description:
            blocks.append(f"Description: {description}")
        stats = _format_repo_stats(repo)
        if stats:
            blocks.append(stats)
        topics = repo.get("topics")
        if isinstance(topics, list) and topics:
            blocks.append("Topics: " + ", ".join(str(topic).strip() for topic in topics[:8] if str(topic).strip()))
        if readme_text:
            blocks.append("README:\n" + readme_text)
        if release_text:
            blocks.append("Latest release:\n" + release_text)
        content_text = "\n\n".join(block for block in blocks if block).strip()
        if not _is_meaningful_text(content_text):
            return self.fetcher._fallback_summary_payload(
                context,
                source_type="github_repository",
                normalized_url=normalized_url,
                final_url=repo_url,
                error_type="missing_repo_context",
                error_message="github metadata and remote enrichments were both empty",
                trace={"readme": readme_trace, "release": release_trace},
            )

        payload = InsightContentPayload(
            news_item_id=context.news_item_id,
            status="repo_context",
            source_type="github_repository",
            normalized_url=normalized_url,
            final_url=repo_url,
            title=context.title,
            excerpt=description or _first_line(content_text),
            content_text=content_text,
            content_markdown=content_text,
            extractor_name="github_api" if readme_text or release_text else "github_metadata",
            content_hash=_hash_text(content_text),
            trace={
                "cache_hit": False,
                "readme": readme_trace,
                "release": release_trace,
            },
        )
        self.fetcher._save_payload(context, payload)
        return payload

    async def _fetch_hackernews_context(
        self,
        session: aiohttp.ClientSession,
        context: InsightNewsContext,
    ) -> InsightContentPayload:
        target_url = str(context.url or context.mobile_url or "").strip()
        if not target_url:
            return self.fetcher._fallback_summary_payload(
                context,
                source_type="hackernews_item",
                error_type="missing_url",
                error_message="hackernews item does not have a thread URL",
            )
        if "news.ycombinator.com" not in target_url and "hn.aimaker.dev" not in target_url:
            return await self._fetch_article_context(session, context, override_url=target_url, source_type="hackernews_external")

        try:
            html, _, _ = await self._request_text(session, target_url)
        except Exception as exc:
            return self.fetcher._fallback_summary_payload(
                context,
                source_type="hackernews_item",
                normalized_url=normalize_url(target_url, context.source_id),
                final_url=target_url,
                error_type="request_failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        external_url = _extract_hn_external_url(html)
        if external_url:
            external_payload = await self._fetch_article_context(
                session,
                context,
                override_url=external_url,
                source_type="hackernews_external",
            )
            if external_payload.status in {"ok", "repo_context"}:
                return replace(
                    external_payload,
                    trace={**dict(external_payload.trace), "hn_thread_url": target_url, "route": "external_link"},
                )

        hn_text = _extract_hn_item_text(html)
        normalized_url = normalize_url(target_url, context.source_id)
        if _is_meaningful_text(hn_text):
            payload = InsightContentPayload(
                news_item_id=context.news_item_id,
                status="hn_item_text",
                source_type="hackernews_item",
                normalized_url=normalized_url,
                final_url=target_url,
                title=context.title,
                excerpt=_first_line(hn_text),
                content_text=hn_text,
                content_markdown=hn_text,
                extractor_name="hn_page_parser",
                content_hash=_hash_text(hn_text),
                trace={"cache_hit": False, "route": "hn_thread_text"},
            )
            self.fetcher._save_payload(context, payload)
            return payload

        return self.fetcher._fallback_summary_payload(
            context,
            source_type="hackernews_item",
            normalized_url=normalized_url,
            final_url=target_url,
            error_type="hn_empty_content",
            error_message="both external link extraction and hn thread text extraction failed",
        )

    async def _fetch_github_readme(
        self,
        session: aiohttp.ClientSession,
        full_name: str,
    ) -> tuple[str, dict[str, Any]]:
        if not full_name:
            return "", {"status": "skipped", "reason": "missing_full_name"}
        headers = {"Accept": "application/vnd.github.raw+json"}
        if self.fetcher.github_token:
            headers["Authorization"] = f"Bearer {self.fetcher.github_token}"
        try:
            text, _, status_code = await self._request_text(
                session,
                f"https://api.github.com/repos/{quote(full_name, safe='/')}/readme",
                headers=headers,
            )
            return _trim_text(text, limit=4000), {"status": "ok", "status_code": status_code, "length": len(text)}
        except aiohttp.ClientResponseError as exc:
            return "", {"status": "http_error", "status_code": exc.status}
        except Exception as exc:
            return "", {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    async def _fetch_github_latest_release(
        self,
        session: aiohttp.ClientSession,
        full_name: str,
    ) -> tuple[str, dict[str, Any]]:
        if not full_name:
            return "", {"status": "skipped", "reason": "missing_full_name"}
        headers = {"Accept": "application/vnd.github+json"}
        if self.fetcher.github_token:
            headers["Authorization"] = f"Bearer {self.fetcher.github_token}"
        try:
            payload, status_code = await self._request_json(
                session,
                f"https://api.github.com/repos/{quote(full_name, safe='/')}/releases/latest",
                headers=headers,
            )
            body = _trim_text(strip_html(str(payload.get("body") or "")), limit=2000)
            if not body:
                return "", {"status": "empty", "status_code": status_code}
            name = str(payload.get("name") or payload.get("tag_name") or "").strip()
            if name:
                body = f"{name}\n{body}"
            return body, {"status": "ok", "status_code": status_code, "length": len(body)}
        except aiohttp.ClientResponseError as exc:
            return "", {"status": "http_error", "status_code": exc.status}
        except Exception as exc:
            return "", {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    async def _request_text(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, str, int]:
        async with session.get(url, headers=headers, proxy=self.fetcher.proxy_url or None) as response:
            response.raise_for_status()
            return await response.text(), str(response.url or url), int(response.status)

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], int]:
        async with session.get(url, headers=headers, proxy=self.fetcher.proxy_url or None) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
            return dict(payload or {}), int(response.status)
