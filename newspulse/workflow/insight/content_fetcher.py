# coding=utf-8
"""Source-aware content fetching for the insight stage."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from typing import Any, Mapping, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from newspulse.crawler.sources.base import DEFAULT_HEADERS, strip_html
from newspulse.storage import ArticleContentRecord
from newspulse.utils.url import normalize_url
from newspulse.workflow.insight.content_extractors import ContentExtractor, build_default_extractors
from newspulse.workflow.insight.models import ExtractedContent, InsightContentPayload, InsightNewsContext


class InsightContentFetcher:
    """Fetch article or equivalent content only for the final selected news items."""

    def __init__(
        self,
        *,
        storage_manager: Any | None = None,
        extractors: list[ContentExtractor] | None = None,
        timeout: int = 12,
        proxy_url: str | None = None,
        github_token: str | None = None,
        cache_enabled: bool = True,
        session: requests.Session | None = None,
    ):
        self.storage_manager = storage_manager
        self.extractors = list(extractors or build_default_extractors())
        self.timeout = max(3, int(timeout or 12))
        self.cache_enabled = bool(cache_enabled)
        self.github_token = str(github_token or os.environ.get('GITHUB_API_TOKEN', '') or '').strip()
        self.session = session or requests.Session()
        self.session.headers.update(dict(DEFAULT_HEADERS))
        if proxy_url:
            self.session.proxies.update({'http': proxy_url, 'https': proxy_url})

    def fetch_many(self, contexts: list[InsightNewsContext]) -> list[InsightContentPayload]:
        return [self.fetch_one(context) for context in contexts]

    def fetch_one(self, context: InsightNewsContext) -> InsightContentPayload:
        source_kind = str(context.source_context.source_kind or '').strip()
        if source_kind == 'github_repository':
            return self._fetch_github_context(context)
        if source_kind == 'hackernews_item':
            return self._fetch_hackernews_context(context)
        return self._fetch_article_context(context)

    def _fetch_article_context(
        self,
        context: InsightNewsContext,
        *,
        override_url: str | None = None,
        source_type: str = 'article',
    ) -> InsightContentPayload:
        target_url = str(override_url or context.url or context.mobile_url or '').strip()
        if not target_url:
            return self._fallback_summary_payload(
                context,
                source_type=source_type,
                error_type='missing_url',
                error_message='content route does not have a usable URL',
            )

        normalized_url = normalize_url(target_url, context.source_id)
        cached = self._load_cached(normalized_url, context.news_item_id)
        if cached is not None:
            return cached

        try:
            response = self.session.get(target_url, timeout=self.timeout)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url or target_url)
        except Exception as exc:
            return self._fallback_summary_payload(
                context,
                source_type=source_type,
                normalized_url=normalized_url,
                final_url=target_url,
                error_type='request_failed',
                error_message=f'{type(exc).__name__}: {exc}',
            )

        attempts: list[dict[str, Any]] = []
        for extractor in self.extractors:
            extracted = extractor.extract(url=final_url, html=html)
            attempts.append(
                {
                    'extractor': extractor.name,
                    'success': extracted.success,
                    'error_type': extracted.error_type,
                    'error_message': extracted.error_message,
                    'text_length': len(extracted.text or ''),
                }
            )
            if extracted.success and _is_meaningful_text(extracted.text):
                payload = InsightContentPayload(
                    news_item_id=context.news_item_id,
                    status='ok',
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
                        'cache_hit': False,
                        'http_status': int(getattr(response, 'status_code', 200) or 200),
                        'attempts': attempts,
                    },
                )
                self._save_payload(context, payload)
                return payload

        last_attempt = attempts[-1] if attempts else {}
        return self._fallback_summary_payload(
            context,
            source_type=source_type,
            normalized_url=normalized_url,
            final_url=final_url,
            error_type=str(last_attempt.get('error_type', 'extract_failed') or 'extract_failed'),
            error_message=str(last_attempt.get('error_message', 'all extractors returned empty content') or ''),
            trace={'cache_hit': False, 'attempts': attempts},
        )

    def _fetch_github_context(self, context: InsightNewsContext) -> InsightContentPayload:
        repo = dict(context.source_context.metadata or {})
        full_name = str(repo.get('full_name') or context.title or '').strip()
        repo_url = str(context.url or f'https://github.com/{full_name}' if full_name else '').strip()
        normalized_url = normalize_url(repo_url, context.source_id)
        cached = self._load_cached(normalized_url, context.news_item_id)
        if cached is not None:
            return cached

        readme_text, readme_trace = self._fetch_github_readme(full_name)
        release_text, release_trace = self._fetch_github_latest_release(full_name)
        blocks: list[str] = []
        if full_name:
            blocks.append(f'Repository: {full_name}')
        description = str(repo.get('description') or context.source_context.summary or '').strip()
        if description:
            blocks.append(f'Description: {description}')
        stats = _format_repo_stats(repo)
        if stats:
            blocks.append(stats)
        topics = repo.get('topics')
        if isinstance(topics, list) and topics:
            blocks.append('Topics: ' + ', '.join(str(topic).strip() for topic in topics[:8] if str(topic).strip()))
        if readme_text:
            blocks.append('README:\n' + readme_text)
        if release_text:
            blocks.append('Latest release:\n' + release_text)
        content_text = '\n\n'.join(block for block in blocks if block).strip()
        if not _is_meaningful_text(content_text):
            return self._fallback_summary_payload(
                context,
                source_type='github_repository',
                normalized_url=normalized_url,
                final_url=repo_url,
                error_type='missing_repo_context',
                error_message='github metadata and remote enrichments were both empty',
                trace={'readme': readme_trace, 'release': release_trace},
            )

        payload = InsightContentPayload(
            news_item_id=context.news_item_id,
            status='repo_context',
            source_type='github_repository',
            normalized_url=normalized_url,
            final_url=repo_url,
            title=context.title,
            excerpt=description or _first_line(content_text),
            content_text=content_text,
            content_markdown=content_text,
            extractor_name='github_api' if readme_text or release_text else 'github_metadata',
            content_hash=_hash_text(content_text),
            trace={
                'cache_hit': False,
                'readme': readme_trace,
                'release': release_trace,
            },
        )
        self._save_payload(context, payload)
        return payload

    def _fetch_hackernews_context(self, context: InsightNewsContext) -> InsightContentPayload:
        target_url = str(context.url or context.mobile_url or '').strip()
        if not target_url:
            return self._fallback_summary_payload(
                context,
                source_type='hackernews_item',
                error_type='missing_url',
                error_message='hackernews item does not have a thread URL',
            )
        if 'news.ycombinator.com' not in target_url and 'hn.aimaker.dev' not in target_url:
            return self._fetch_article_context(context, override_url=target_url, source_type='hackernews_external')

        try:
            response = self.session.get(target_url, timeout=self.timeout)
            response.raise_for_status()
            html = response.text
        except Exception as exc:
            return self._fallback_summary_payload(
                context,
                source_type='hackernews_item',
                normalized_url=normalize_url(target_url, context.source_id),
                final_url=target_url,
                error_type='request_failed',
                error_message=f'{type(exc).__name__}: {exc}',
            )

        external_url = _extract_hn_external_url(html)
        if external_url:
            external_payload = self._fetch_article_context(
                context,
                override_url=external_url,
                source_type='hackernews_external',
            )
            if external_payload.status in {'ok', 'repo_context'}:
                return replace(
                    external_payload,
                    trace={**dict(external_payload.trace), 'hn_thread_url': target_url, 'route': 'external_link'},
                )

        hn_text = _extract_hn_item_text(html)
        normalized_url = normalize_url(target_url, context.source_id)
        if _is_meaningful_text(hn_text):
            payload = InsightContentPayload(
                news_item_id=context.news_item_id,
                status='hn_item_text',
                source_type='hackernews_item',
                normalized_url=normalized_url,
                final_url=target_url,
                title=context.title,
                excerpt=_first_line(hn_text),
                content_text=hn_text,
                content_markdown=hn_text,
                extractor_name='hn_page_parser',
                content_hash=_hash_text(hn_text),
                trace={'cache_hit': False, 'route': 'hn_thread_text'},
            )
            self._save_payload(context, payload)
            return payload

        return self._fallback_summary_payload(
            context,
            source_type='hackernews_item',
            normalized_url=normalized_url,
            final_url=target_url,
            error_type='hn_empty_content',
            error_message='both external link extraction and hn thread text extraction failed',
        )

    def _fetch_github_readme(self, full_name: str) -> tuple[str, dict[str, Any]]:
        if not full_name:
            return '', {'status': 'skipped', 'reason': 'missing_full_name'}
        headers = {'Accept': 'application/vnd.github.raw+json'}
        if self.github_token:
            headers['Authorization'] = f'Bearer {self.github_token}'
        try:
            response = self.session.get(
                f'https://api.github.com/repos/{quote(full_name, safe="/")}/readme',
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                return '', {'status': 'http_error', 'status_code': response.status_code}
            text = _trim_text(response.text, limit=4000)
            return text, {'status': 'ok', 'length': len(text)}
        except Exception as exc:
            return '', {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}

    def _fetch_github_latest_release(self, full_name: str) -> tuple[str, dict[str, Any]]:
        if not full_name:
            return '', {'status': 'skipped', 'reason': 'missing_full_name'}
        headers = {'Accept': 'application/vnd.github+json'}
        if self.github_token:
            headers['Authorization'] = f'Bearer {self.github_token}'
        try:
            response = self.session.get(
                f'https://api.github.com/repos/{quote(full_name, safe="/")}/releases/latest',
                headers=headers,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                return '', {'status': 'http_error', 'status_code': response.status_code}
            payload = response.json()
            body = _trim_text(strip_html(str(payload.get('body') or '')), limit=2000)
            if not body:
                return '', {'status': 'empty'}
            name = str(payload.get('name') or payload.get('tag_name') or '').strip()
            if name:
                body = f'{name}\n{body}'
            return body, {'status': 'ok', 'length': len(body)}
        except Exception as exc:
            return '', {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}

    def _load_cached(self, normalized_url: str, news_item_id: str) -> Optional[InsightContentPayload]:
        if not self.cache_enabled or not normalized_url or self.storage_manager is None:
            return None
        record = self.storage_manager.get_article_content(normalized_url)
        if record is None:
            return None
        return InsightContentPayload(
            news_item_id=news_item_id,
            status=record.fetch_status or 'cached',
            source_type=record.source_type,
            normalized_url=record.normalized_url,
            final_url=record.final_url,
            title=record.title,
            excerpt=record.excerpt,
            content_text=record.content_text,
            content_markdown=record.content_markdown,
            published_at=record.published_at,
            author=record.author,
            extractor_name=record.extractor_name,
            content_hash=record.content_hash,
            error_type=record.error_type,
            error_message=record.error_message,
            trace={**dict(record.trace or {}), 'cache_hit': True},
        )

    def _save_payload(self, context: InsightNewsContext, payload: InsightContentPayload) -> None:
        if self.storage_manager is None or not payload.normalized_url:
            return
        record = ArticleContentRecord(
            normalized_url=payload.normalized_url,
            source_type=payload.source_type,
            source_id=context.source_id,
            source_name=context.source_name,
            source_kind=context.source_context.source_kind,
            original_url=context.url or context.mobile_url,
            final_url=payload.final_url,
            title=payload.title,
            excerpt=payload.excerpt,
            content_text=payload.content_text,
            content_markdown=payload.content_markdown,
            content_hash=payload.content_hash,
            published_at=payload.published_at,
            author=payload.author,
            extractor_name=payload.extractor_name,
            fetch_status=payload.status,
            error_type=payload.error_type,
            error_message=payload.error_message,
            trace=dict(payload.trace or {}),
        )
        self.storage_manager.save_article_content(record)

    def _fallback_summary_payload(
        self,
        context: InsightNewsContext,
        *,
        source_type: str,
        normalized_url: str = '',
        final_url: str = '',
        error_type: str = '',
        error_message: str = '',
        trace: Mapping[str, Any] | None = None,
    ) -> InsightContentPayload:
        content_text = _build_summary_fallback_text(context)
        payload = InsightContentPayload(
            news_item_id=context.news_item_id,
            status='fallback_summary_only',
            source_type=source_type,
            normalized_url=normalized_url,
            final_url=final_url or context.url or context.mobile_url,
            title=context.title,
            excerpt=context.source_context.summary,
            content_text=content_text,
            content_markdown=content_text,
            extractor_name='summary_fallback',
            content_hash=_hash_text(content_text),
            error_type=error_type,
            error_message=error_message,
            trace=dict(trace or {}),
        )
        self._save_payload(context, payload)
        return payload


def _build_summary_fallback_text(context: InsightNewsContext) -> str:
    lines = [context.title]
    summary = str(context.source_context.summary or '').strip()
    if summary:
        lines.append(f'Summary: {summary}')
    attributes = [str(line).strip() for line in context.source_context.attributes if str(line).strip()]
    if attributes:
        lines.append('Source context: ' + '; '.join(attributes[:6]))
    evidence = []
    if context.selection_evidence.matched_topics:
        evidence.append('topics=' + ', '.join(context.selection_evidence.matched_topics[:6]))
    if context.selection_evidence.llm_reasons:
        evidence.append('reasons=' + '; '.join(context.selection_evidence.llm_reasons[:4]))
    if context.selection_evidence.quality_score > 0:
        evidence.append(f'quality_score={context.selection_evidence.quality_score:.3f}')
    if context.selection_evidence.semantic_score > 0:
        evidence.append(f'semantic_score={context.selection_evidence.semantic_score:.3f}')
    if evidence:
        lines.append('Selection evidence: ' + ' | '.join(evidence))
    return '\n'.join(line for line in lines if line).strip()


def _extract_hn_external_url(html: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    selectors = [
        '.titleline a[href]',
        'a.titlelink[href]',
        'main a[href^="http"]',
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        href = str(node.get('href') or '').strip() if node else ''
        if href and 'news.ycombinator.com' not in href:
            return href
    return ''


def _extract_hn_item_text(html: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    blocks: list[str] = []
    for selector in ('.toptext', '.comment .commtext', '.comment-tree .commtext'):
        for node in soup.select(selector):
            text = strip_html(str(node))
            cleaned = _trim_text(text, limit=500)
            if cleaned and cleaned not in blocks:
                blocks.append(cleaned)
            if len(blocks) >= 6:
                break
        if blocks:
            break
    return '\n\n'.join(blocks).strip()


def _format_repo_stats(repo: Mapping[str, Any]) -> str:
    parts: list[str] = []
    language = str(repo.get('language') or '').strip()
    if language:
        parts.append(f'language={language}')
    for label, key in (('stars_today', 'stars_today'), ('stars_total', 'stars_total'), ('forks_total', 'forks_total')):
        value = repo.get(key)
        if value not in (None, ''):
            parts.append(f'{label}={value}')
    pushed_at = str(repo.get('pushed_at') or '').strip()
    if pushed_at:
        parts.append(f'updated={pushed_at[:10]}')
    created_at = str(repo.get('created_at') or '').strip()
    if created_at:
        parts.append(f'created={created_at[:10]}')
    flags = []
    if bool(repo.get('archived')):
        flags.append('archived')
    if bool(repo.get('fork')):
        flags.append('fork')
    if flags:
        parts.append('flags=' + ','.join(flags))
    return 'Repo stats: ' + '; '.join(parts) if parts else ''


def _hash_text(text: str) -> str:
    return hashlib.sha1((text or '').encode('utf-8')).hexdigest() if text else ''


def _is_meaningful_text(text: str, min_length: int = 120) -> bool:
    normalized = ' '.join((text or '').split())
    return len(normalized) >= min_length


def _trim_text(text: str, *, limit: int) -> str:
    normalized = ' '.join((text or '').split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + '...'


def _first_line(text: str) -> str:
    for line in str(text or '').splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ''
