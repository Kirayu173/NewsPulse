# coding=utf-8
"""Preprocess fetched content into bounded item-summary context."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from newspulse.workflow.insight.content_models import FetchedContent, ReducedSummaryContext
from newspulse.workflow.insight.models import InsightNewsContext

BOILERPLATE_PATTERNS = (
    "cookie",
    "cookies",
    "privacy policy",
    "subscribe",
    "sign up",
    "sign in",
    "log in",
    "advertisement",
    "all rights reserved",
    "share this",
    "related articles",
    "推荐阅读",
    "相关阅读",
    "点击查看",
    "版权",
    "广告",
    "登录",
    "注册",
)


class ContentPreprocessor:
    """Reduce fetched text before any model prompt sees it."""

    def reduce_many(
        self,
        contexts: Sequence[InsightNewsContext],
        fetched: Mapping[str, FetchedContent],
        *,
        max_chars: int = 6000,
    ) -> tuple[list[ReducedSummaryContext], dict[str, Any]]:
        reduced: list[ReducedSummaryContext] = []
        for context in contexts:
            item_id = str(context.news_item_id or "").strip()
            reduced.append(self.reduce(context, fetched.get(item_id), max_chars=max_chars))

        rows = [dict(row.diagnostics or {}) for row in reduced]
        return reduced, {
            "max_chars": max(1, int(max_chars or 6000)),
            "context_count": len(reduced),
            "total_reduced_chars": sum(row.reduced_char_count for row in reduced),
            "contexts": rows,
        }

    def reduce(
        self,
        context: InsightNewsContext,
        fetched: FetchedContent | None,
        *,
        max_chars: int = 6000,
    ) -> ReducedSummaryContext:
        budget = max(1, int(max_chars or 6000))
        source_context = context.source_context
        evidence = context.selection_evidence
        rank_signals = context.rank_signals
        item_id = str(context.news_item_id or "").strip()
        source_summary = _normalize_text(source_context.summary, limit=min(1000, budget))
        fetched_text = str(getattr(fetched, "text", "") or "")
        fetch_status = str(getattr(fetched, "status", "") or "not_fetched")

        paragraphs = _split_paragraphs(fetched_text)
        clean_paragraphs = _dedupe_paragraphs(
            paragraph
            for paragraph in paragraphs
            if _is_useful_paragraph(paragraph)
        )
        scored = [
            (
                _score_paragraph(
                    paragraph,
                    index=index,
                    context=context,
                ),
                index,
                paragraph,
            )
            for index, paragraph in enumerate(clean_paragraphs)
        ]
        selected_indexes = {
            index
            for _, index, _ in sorted(scored, key=lambda row: (-row[0], row[1]))[:16]
        }
        ordered = [
            _trim_sentence(paragraph, max_chars=max(400, budget // 3))
            for index, paragraph in enumerate(clean_paragraphs)
            if index in selected_indexes
        ]

        excerpt = _normalize_text(getattr(fetched, "excerpt", "") if fetched else "", limit=600)
        key_paragraphs = _fit_budget(
            [paragraph for paragraph in ordered if paragraph],
            max_chars=max(0, budget - len(excerpt) - len(source_summary)),
        )
        reduced = ReducedSummaryContext(
            news_item_id=item_id,
            title=str(context.title or "").strip(),
            source=str(context.source_name or context.source_id or "").strip(),
            url=str(context.url or context.mobile_url or "").strip(),
            source_summary=source_summary,
            extracted_excerpt=excerpt,
            key_paragraphs=key_paragraphs,
            evidence_topics=_compact_values(evidence.matched_topics, limit=8),
            evidence_notes=_compact_values(evidence.llm_reasons, limit=8),
            rank_signals={
                "current_rank": int(rank_signals.current_rank or 0),
                "best_rank": int(rank_signals.best_rank or 0),
                "worst_rank": int(rank_signals.worst_rank or 0),
                "appearance_count": int(rank_signals.appearance_count or 0),
                "rank_trend": str(rank_signals.rank_trend or "").strip(),
                "semantic_score": float(evidence.semantic_score or 0.0),
                "quality_score": float(evidence.quality_score or 0.0),
            },
            metadata={
                "source_id": str(context.source_id or "").strip(),
                "source_attributes": _compact_values(source_context.attributes, limit=8, drop_prefixes=("route:",)),
                "fetch_status": fetch_status,
                "extractor": str(getattr(fetched, "extraction_method", "") or ""),
            },
            diagnostics={
                "news_item_id": item_id,
                "fetch_status": fetch_status,
                "fetch_extractor": str(getattr(fetched, "extraction_method", "") or ""),
                "raw_text_chars": len(fetched_text),
                "paragraph_count": len(paragraphs),
                "deduped_paragraph_count": len(clean_paragraphs),
                "selected_paragraph_count": len(key_paragraphs),
                "reduced_chars": len(excerpt) + sum(len(paragraph) for paragraph in key_paragraphs),
                "max_chars": budget,
                "used_fetched_content": bool(key_paragraphs or excerpt),
            },
        )
        return reduced


def to_prompt_payload(context: ReducedSummaryContext) -> dict[str, Any]:
    """Serialize a reduced context for prompt insertion."""

    payload = asdict(context)
    payload["reduced_text"] = context.reduced_text
    payload["reduced_char_count"] = context.reduced_char_count
    return payload


def _split_paragraphs(text: str) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", str(text or ""))
    normalized = re.sub(r"[ \t]+", " ", normalized)
    candidates = re.split(r"\n{2,}|\n|(?<=[。！？!?])\s+", normalized)
    return [_normalize_text(candidate, limit=2400) for candidate in candidates if _normalize_text(candidate, limit=2400)]


def _is_useful_paragraph(paragraph: str) -> bool:
    text = _normalize_text(paragraph, limit=2400)
    if len(text) < 40:
        return False
    lowered = text.lower()
    if any(pattern in lowered for pattern in BOILERPLATE_PATTERNS):
        return False
    return not _link_or_menu_heavy(text)


def _link_or_menu_heavy(text: str) -> bool:
    words = text.split()
    if not words:
        return False
    slash_count = text.count("/") + text.count("|") + text.count("›")
    return slash_count >= max(6, len(words) // 3)


def _dedupe_paragraphs(paragraphs: Sequence[str] | object) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for paragraph in paragraphs:
        text = _normalize_text(paragraph, limit=2400)
        key = re.sub(r"\W+", "", text.lower())[:200]
        if not text or key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows


def _score_paragraph(paragraph: str, *, index: int, context: InsightNewsContext) -> float:
    text = paragraph.lower()
    score = 0.0
    title_terms = _important_terms(context.title)
    topic_terms = [
        term
        for topic in context.selection_evidence.matched_topics
        for term in _important_terms(topic)
    ]
    reason_terms = [
        term
        for reason in context.selection_evidence.llm_reasons
        for term in _important_terms(reason)
    ]
    score += sum(2.5 for term in title_terms if term in text)
    score += sum(2.0 for term in topic_terms if term in text)
    score += sum(1.0 for term in reason_terms if term in text)
    length = len(paragraph)
    if 120 <= length <= 900:
        score += 3
    elif length > 900:
        score += 1
    score += max(0, 4 - index * 0.25)
    return score


def _important_terms(value: object) -> list[str]:
    text = str(value or "").lower()
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text)
    return [token for token in tokens if token not in {"the", "and", "for", "with", "from"}][:12]


def _trim_sentence(text: str, *, max_chars: int) -> str:
    normalized = _normalize_text(text, limit=max_chars)
    if len(normalized) < max_chars:
        return normalized
    sentence_parts = re.split(r"(?<=[。！？!?])", normalized)
    result = ""
    for part in sentence_parts:
        if len(result) + len(part) > max_chars:
            break
        result += part
    return result.strip() or normalized[:max_chars].rstrip()


def _fit_budget(paragraphs: Sequence[str], *, max_chars: int) -> list[str]:
    budget = max(0, int(max_chars or 0))
    if budget <= 0:
        return []
    rows: list[str] = []
    used = 0
    for paragraph in paragraphs:
        text = _normalize_text(paragraph, limit=budget)
        if not text:
            continue
        remaining = budget - used
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = _trim_sentence(text, max_chars=remaining)
        if text:
            rows.append(text)
            used += len(text)
    return rows


def _compact_values(
    values: Sequence[str] | tuple[str, ...],
    *,
    limit: int,
    drop_prefixes: tuple[str, ...] = (),
) -> list[str]:
    normalized: list[str] = []
    for raw in values or ():
        text = _normalize_text(raw, limit=120)
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in drop_prefixes):
            continue
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_text(value: object, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
