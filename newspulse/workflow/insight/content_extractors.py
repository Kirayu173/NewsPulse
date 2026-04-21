# coding=utf-8
"""Native wrappers around third-party content extraction libraries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bs4 import BeautifulSoup
from readability import Document

from newspulse.crawler.sources.base import strip_html
from newspulse.workflow.insight.models import ExtractedContent


class ContentExtractor(Protocol):
    """Protocol shared by all extractor adapters."""

    name: str

    def extract(self, *, url: str, html: str) -> ExtractedContent:
        """Extract normalized content from fetched HTML."""


@dataclass(frozen=True)
class TrafilaturaExtractor:
    """Adapter for `trafilatura`."""

    name: str = 'trafilatura'

    def extract(self, *, url: str, html: str) -> ExtractedContent:
        try:
            import trafilatura  # type: ignore
        except Exception as exc:
            return _extractor_error(self.name, 'dependency_unavailable', exc)

        try:
            text = str(
                trafilatura.extract(
                    html,
                    url=url,
                    include_comments=False,
                    include_tables=False,
                    output_format='txt',
                )
                or ''
            ).strip()
            if not text:
                return ExtractedContent(
                    success=False,
                    extractor_name=self.name,
                    error_type='empty_content',
                    error_message='trafilatura returned empty text',
                )
            metadata = None
            try:
                metadata = trafilatura.extract_metadata(html, url=url)
            except Exception:
                metadata = None
            title = str(getattr(metadata, 'title', '') or _extract_title_from_html(html)).strip()
            excerpt = _first_excerpt(text)
            published_at = str(getattr(metadata, 'date', '') or '').strip()
            author = str(getattr(metadata, 'author', '') or '').strip()
            return ExtractedContent(
                success=True,
                title=title,
                excerpt=excerpt,
                text=text,
                markdown=text,
                final_url=url,
                published_at=published_at,
                author=author,
                extractor_name=self.name,
                trace={'backend': 'trafilatura'},
            )
        except Exception as exc:
            return _extractor_error(self.name, 'extract_failed', exc)


@dataclass(frozen=True)
class GooseExtractor:
    """Adapter for `goose3`."""

    name: str = 'goose3'

    def extract(self, *, url: str, html: str) -> ExtractedContent:
        try:
            from goose3 import Goose  # type: ignore
        except Exception as exc:
            return _extractor_error(self.name, 'dependency_unavailable', exc)

        try:
            goose = Goose()
            article = goose.extract(raw_html=html)
            text = str(getattr(article, 'cleaned_text', '') or '').strip()
            if not text:
                return ExtractedContent(
                    success=False,
                    extractor_name=self.name,
                    error_type='empty_content',
                    error_message='goose3 returned empty text',
                )
            title = str(getattr(article, 'title', '') or _extract_title_from_html(html)).strip()
            excerpt = str(getattr(article, 'meta_description', '') or _first_excerpt(text)).strip()
            publish_date = getattr(article, 'publish_date', None)
            return ExtractedContent(
                success=True,
                title=title,
                excerpt=excerpt,
                text=text,
                markdown=text,
                final_url=url,
                published_at=str(publish_date or '').strip(),
                author=str(getattr(article, 'authors', '') or '').strip(),
                extractor_name=self.name,
                trace={'backend': 'goose3'},
            )
        except Exception as exc:
            return _extractor_error(self.name, 'extract_failed', exc)


@dataclass(frozen=True)
class ReadabilityExtractor:
    """Adapter for `readability-lxml`."""

    name: str = 'readability'

    def extract(self, *, url: str, html: str) -> ExtractedContent:
        try:
            document = Document(html)
            summary_html = str(document.summary(html_partial=True) or '').strip()
            text = strip_html(summary_html).strip()
            if not text:
                return ExtractedContent(
                    success=False,
                    extractor_name=self.name,
                    error_type='empty_content',
                    error_message='readability returned empty text',
                )
            return ExtractedContent(
                success=True,
                title=str(document.short_title() or document.title() or _extract_title_from_html(html)).strip(),
                excerpt=_first_excerpt(text),
                text=text,
                markdown=text,
                final_url=url,
                extractor_name=self.name,
                trace={'backend': 'readability', 'summary_html_length': len(summary_html)},
            )
        except Exception as exc:
            return _extractor_error(self.name, 'extract_failed', exc)


def build_default_extractors(names: list[str] | tuple[str, ...] | None = None) -> list[ContentExtractor]:
    """Build the project-owned extractor chain in configured order."""

    configured = [str(name or '').strip().lower() for name in (names or ('trafilatura', 'goose3', 'readability'))]
    mapping = {
        'trafilatura': TrafilaturaExtractor(),
        'goose3': GooseExtractor(),
        'goose': GooseExtractor(),
        'readability': ReadabilityExtractor(),
        'readability-lxml': ReadabilityExtractor(),
    }
    return [mapping[name] for name in configured if name in mapping]


def _extractor_error(name: str, error_type: str, exc: Exception) -> ExtractedContent:
    return ExtractedContent(
        success=False,
        extractor_name=name,
        error_type=error_type,
        error_message=f'{type(exc).__name__}: {exc}',
    )


def _extract_title_from_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    return str(title or '').strip()


def _first_excerpt(text: str, limit: int = 240) -> str:
    normalized = ' '.join((text or '').split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + '...'
