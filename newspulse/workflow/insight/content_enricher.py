# coding=utf-8
"""Lightweight HTTP content enrichment for item summaries."""

from __future__ import annotations

import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from newspulse.workflow.insight.content_models import FetchedContent
from newspulse.workflow.insight.models import InsightNewsContext

DEFAULT_EXTRACTOR_ORDER = ("trafilatura", "readability", "beautifulsoup")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsPulse/1.0; +https://github.com/news-pulse)"
)


class ContentFetchEnricher:
    """Fetch and extract article text without invoking the old heavy insight path."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        timeout_seconds: int = 8,
        max_raw_chars: int = 120_000,
        extractor_order: Sequence[str] = DEFAULT_EXTRACTOR_ORDER,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Any | None = None,
    ):
        self.enabled = bool(enabled)
        self.timeout_seconds = max(1, int(timeout_seconds or 8))
        self.max_raw_chars = max(1_000, int(max_raw_chars or 120_000))
        self.extractor_order = tuple(
            str(name or "").strip().lower()
            for name in extractor_order
            if str(name or "").strip()
        ) or DEFAULT_EXTRACTOR_ORDER
        self.user_agent = user_agent
        self.client = client

    def fetch_many(
        self,
        contexts: Sequence[InsightNewsContext],
        *,
        max_workers: int = 3,
    ) -> tuple[dict[str, FetchedContent], dict[str, Any]]:
        if not self.enabled:
            return {}, {
                "enabled": False,
                "attempted_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": len(contexts),
                "results": [],
            }

        workers = max(1, int(max_workers or 1))
        fetched: dict[str, FetchedContent] = {}
        rows: list[dict[str, Any]] = []
        target_contexts = [
            context
            for context in contexts
            if str(context.news_item_id or "").strip()
            and str(context.url or context.mobile_url or "").strip()
        ]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(self._fetch_one, context): context
                for context in target_contexts
            }
            for future in as_completed(future_map):
                context = future_map[future]
                item_id = str(context.news_item_id or "").strip()
                try:
                    content = future.result()
                except Exception as exc:  # pragma: no cover - defensive boundary
                    content = FetchedContent(
                        news_item_id=item_id,
                        url=str(context.url or context.mobile_url or "").strip(),
                        status="failed",
                        diagnostics={
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        },
                    )
                fetched[item_id] = content
                rows.append(_diagnostic_row(content))

        skipped_count = len(contexts) - len(target_contexts)
        success_count = sum(1 for row in rows if row.get("status") == "ok")
        failed_count = sum(1 for row in rows if row.get("status") != "ok")
        return fetched, {
            "enabled": True,
            "attempted_count": len(target_contexts),
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "max_workers": workers,
            "timeout_seconds": self.timeout_seconds,
            "max_raw_chars": self.max_raw_chars,
            "extractor_order": list(self.extractor_order),
            "results": rows,
        }

    def _fetch_one(self, context: InsightNewsContext) -> FetchedContent:
        item_id = str(context.news_item_id or "").strip()
        url = str(context.url or context.mobile_url or "").strip()
        started = time.perf_counter()
        if not url.startswith(("http://", "https://")):
            return FetchedContent(
                news_item_id=item_id,
                url=url,
                status="skipped",
                diagnostics={"reason": "unsupported_url"},
            )

        try:
            html, status_code, content_type = self._http_get(url)
        except Exception as exc:
            return FetchedContent(
                news_item_id=item_id,
                url=url,
                status="failed",
                diagnostics={
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "elapsed_ms": _elapsed_ms(started),
                },
            )

        normalized_content_type = str(content_type or "").lower()
        if normalized_content_type and not any(
            marker in normalized_content_type
            for marker in ("text/html", "application/xhtml", "text/plain")
        ):
            return FetchedContent(
                news_item_id=item_id,
                url=url,
                status="skipped",
                diagnostics={
                    "reason": "unsupported_content_type",
                    "status_code": status_code,
                    "content_type": content_type,
                    "elapsed_ms": _elapsed_ms(started),
                },
            )

        raw_html = str(html or "")[: self.max_raw_chars]
        extraction = self._extract(raw_html, url=url)
        text = str(extraction.get("text", "") or "").strip()
        status = "ok" if text else "failed"
        diagnostics = {
            "status_code": status_code,
            "content_type": content_type,
            "raw_chars": len(raw_html),
            "text_chars": len(text),
            "extractor": extraction.get("extractor", ""),
            "elapsed_ms": _elapsed_ms(started),
        }
        if not text:
            diagnostics["reason"] = "empty_extracted_text"

        return FetchedContent(
            news_item_id=item_id,
            url=url,
            status=status,
            title=str(extraction.get("title", "") or "").strip(),
            byline=str(extraction.get("byline", "") or "").strip(),
            published_at=str(extraction.get("published_at", "") or "").strip(),
            excerpt=str(extraction.get("excerpt", "") or "").strip(),
            text=text,
            markdown=str(extraction.get("markdown", "") or "").strip(),
            extraction_method=str(extraction.get("extractor", "") or "").strip(),
            diagnostics=diagnostics,
        )

    def _http_get(self, url: str) -> tuple[str, int, str]:
        if self.client is not None:
            response = self.client.get(url)
            status_code = int(getattr(response, "status_code", 0) or 0)
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            headers = getattr(response, "headers", {}) or {}
            return str(getattr(response, "text", "") or ""), status_code, str(headers.get("content-type", "") or "")

        try:
            import httpx

            with httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text, int(response.status_code), str(response.headers.get("content-type", "") or "")
        except ImportError:  # pragma: no cover - stdlib fallback for constrained envs
            from urllib.request import Request, urlopen

            request = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read(self.max_raw_chars)
                content_type = response.headers.get("content-type", "")
                return raw.decode("utf-8", errors="replace"), int(response.status), content_type

    def _extract(self, html: str, *, url: str) -> dict[str, Any]:
        for extractor in self.extractor_order:
            if extractor == "trafilatura":
                result = _extract_with_trafilatura(html, url=url)
            elif extractor == "readability":
                result = _extract_with_readability(html)
            elif extractor in {"beautifulsoup", "bs4"}:
                result = _extract_with_beautifulsoup(html)
            else:
                result = {}
            if result.get("text"):
                result["extractor"] = extractor
                return result
        return {"extractor": "", "text": ""}


def _extract_with_trafilatura(html: str, *, url: str) -> dict[str, Any]:
    try:
        import trafilatura
        from trafilatura.metadata import extract_metadata
    except ImportError:
        return {}

    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text:
        return {}
    metadata = extract_metadata(html, default_url=url)
    return {
        "title": getattr(metadata, "title", "") if metadata else "",
        "byline": getattr(metadata, "author", "") if metadata else "",
        "published_at": getattr(metadata, "date", "") if metadata else "",
        "excerpt": getattr(metadata, "description", "") if metadata else "",
        "text": text,
    }


def _extract_with_readability(html: str) -> dict[str, Any]:
    try:
        from readability import Document
    except ImportError:
        return {}

    document = Document(html)
    title = str(document.short_title() or document.title() or "").strip()
    summary_html = document.summary(html_partial=True)
    text = _html_to_text(summary_html)
    if not text:
        return {}
    return {"title": title, "text": text}


def _extract_with_beautifulsoup(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    article = soup.find("article") or soup.body or soup
    text = article.get_text("\n", strip=True)
    return {"title": title, "text": unescape(text)}


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()
    return unescape(soup.get_text("\n", strip=True))


def _diagnostic_row(content: FetchedContent) -> dict[str, Any]:
    diagnostics = dict(content.diagnostics or {})
    return {
        "news_item_id": content.news_item_id,
        "url": content.url,
        "status": content.status,
        "extractor": content.extraction_method or diagnostics.get("extractor", ""),
        "raw_chars": int(diagnostics.get("raw_chars", 0) or 0),
        "text_chars": int(diagnostics.get("text_chars", 0) or 0),
        "reason": str(diagnostics.get("reason", "") or ""),
        "error_type": str(diagnostics.get("error_type", "") or ""),
        "elapsed_ms": int(diagnostics.get("elapsed_ms", 0) or 0),
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
