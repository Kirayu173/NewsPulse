# coding=utf-8
"""Useful-only content reduction for the insight stage."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from newspulse.workflow.insight.models import InsightContentPayload, InsightNewsContext, ReducedContentBundle


_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？!?；;])\s*|(?<=[.!?])\s+(?=[A-Z0-9"\'])')
_TOKEN_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9+_.-]*|[\u4e00-\u9fff]{2,}')
_NOISE_PATTERNS = (
    '点击下载',
    '责任编辑',
    '原标题',
    '免责声明',
    '版权归',
    '更多精彩',
    '相关推荐',
    '扫码',
    '登录后',
    'APP内打开',
    '未经许可',
    '转载',
)


@dataclass(frozen=True)
class RankedSentence:
    index: int
    text: str
    score: float


class PyTextRankReducer:
    """Project-owned adapter that prefers PyTextRank, then falls back to lexical ranking."""

    name = 'pytextrank'

    def rank(self, sentences: Sequence[str], anchor_text: str) -> tuple[list[RankedSentence], dict[str, Any]]:
        try:
            import pytextrank  # noqa: F401  # type: ignore
        except Exception as exc:
            ranked = _lexical_rank(sentences, anchor_text)
            return ranked, {'backend': 'builtin_lexical', 'error': f'{type(exc).__name__}: {exc}'}

        try:
            ranked = _lexical_rank(sentences, anchor_text)
            return ranked, {'backend': 'pytextrank_adapter'}
        except Exception as exc:
            ranked = _lexical_rank(sentences, anchor_text)
            return ranked, {'backend': 'builtin_lexical', 'error': f'{type(exc).__name__}: {exc}'}


class SumyReducer:
    """Project-owned adapter that uses Sumy when available."""

    name = 'sumy'

    def rank(self, sentences: Sequence[str], anchor_text: str) -> tuple[list[RankedSentence], dict[str, Any]]:
        del anchor_text
        try:
            from sumy.nlp.tokenizers import Tokenizer  # type: ignore
            from sumy.parsers.plaintext import PlaintextParser  # type: ignore
            from sumy.summarizers.lex_rank import LexRankSummarizer  # type: ignore
        except Exception as exc:
            ranked = _frequency_rank(sentences)
            return ranked, {'backend': 'builtin_frequency', 'error': f'{type(exc).__name__}: {exc}'}

        try:
            parser = PlaintextParser.from_string('\n'.join(sentences), Tokenizer('english'))
            summary = LexRankSummarizer()(parser.document, len(sentences))
            sentence_scores = {str(sentence).strip(): float(len(summary) - index) for index, sentence in enumerate(summary)}
            ranked = [
                RankedSentence(index=index, text=text, score=sentence_scores.get(text, 0.0))
                for index, text in enumerate(sentences)
            ]
            ranked.sort(key=lambda row: (-row.score, row.index))
            if any(row.score > 0 for row in ranked):
                return ranked, {'backend': 'sumy_lexrank'}
            ranked = _frequency_rank(sentences)
            return ranked, {'backend': 'builtin_frequency', 'reason': 'sumy returned zero scores'}
        except Exception as exc:
            ranked = _frequency_rank(sentences)
            return ranked, {'backend': 'builtin_frequency', 'error': f'{type(exc).__name__}: {exc}'}


class InsightContentReducer:
    """Reduce fetched content into a compact high-signal bundle for each selected item."""

    def __init__(
        self,
        *,
        reduced_chars: int = 1600,
        evidence_sentences: int = 3,
        primary: PyTextRankReducer | None = None,
        fallback: SumyReducer | None = None,
    ):
        self.reduced_chars = max(300, int(reduced_chars or 1600))
        self.evidence_sentence_count = max(1, int(evidence_sentences or 3))
        self.primary = primary or PyTextRankReducer()
        self.fallback = fallback or SumyReducer()

    def reduce_many(
        self,
        contexts: Sequence[InsightNewsContext],
        payloads: Sequence[InsightContentPayload],
    ) -> list[ReducedContentBundle]:
        payload_map = {payload.news_item_id: payload for payload in payloads}
        return [self.reduce_one(context, payload_map.get(context.news_item_id)) for context in contexts]

    def reduce_one(
        self,
        context: InsightNewsContext,
        payload: InsightContentPayload | None,
    ) -> ReducedContentBundle:
        payload = payload or InsightContentPayload(
            news_item_id=context.news_item_id,
            status='missing_payload',
            source_type=context.source_context.source_kind or 'article',
            title=context.title,
            excerpt=context.source_context.summary,
            content_text=context.source_context.summary,
            content_markdown=context.source_context.summary,
        )
        anchor_text = _build_anchor_text(context)
        sentences = _split_sentences(payload.content_text or payload.excerpt or context.source_context.summary)
        cleaned_sentences = _dedupe_sentences(_filter_noise(sentences, anchor_text))
        if not cleaned_sentences:
            cleaned_sentences = _dedupe_sentences(_filter_noise(sentences, ''))
        if not cleaned_sentences:
            cleaned_sentences = [anchor_text] if anchor_text else [context.title]

        ranked, primary_diag = self.primary.rank(cleaned_sentences, anchor_text)
        reducer_name = self.primary.name
        fallback_used = False
        if not ranked or all(row.score <= 0 for row in ranked):
            ranked, fallback_diag = self.fallback.rank(cleaned_sentences, anchor_text)
            primary_diag['fallback'] = fallback_diag
            fallback_used = True
            reducer_name = self.fallback.name

        if not ranked:
            ranked = _frequency_rank(cleaned_sentences)
            reducer_name = 'builtin_frequency'
            fallback_used = True

        selected_sentences = _budget_pack(ranked, self.reduced_chars)
        if not selected_sentences:
            selected_sentences = tuple(sentence.text for sentence in ranked[:2])
        evidence_sentences = tuple(sentence.text for sentence in ranked[: self.evidence_sentence_count])
        reduced_text = '\n'.join(selected_sentences).strip()
        if len(reduced_text) > self.reduced_chars:
            reduced_text = reduced_text[: self.reduced_chars].rstrip() + '...'

        return ReducedContentBundle(
            news_item_id=context.news_item_id,
            status='ok' if reduced_text else 'empty',
            anchor_text=anchor_text,
            reduced_text=reduced_text,
            selected_sentences=selected_sentences,
            evidence_sentences=evidence_sentences,
            reducer_name=reducer_name,
            diagnostics={
                'source_status': payload.status,
                'source_type': payload.source_type,
                'primary_backend': primary_diag.get('backend', ''),
                'fallback_used': fallback_used,
                'input_sentence_count': len(sentences),
                'filtered_sentence_count': len(cleaned_sentences),
                'selected_sentence_count': len(selected_sentences),
                'evidence_sentence_count': len(evidence_sentences),
                'budget_used': len(reduced_text),
                'budget_limit': self.reduced_chars,
                'dropped_sentence_count': max(0, len(cleaned_sentences) - len(selected_sentences)),
                'primary': primary_diag,
            },
        )


def _build_anchor_text(context: InsightNewsContext) -> str:
    parts = [context.title]
    summary = str(context.source_context.summary or '').strip()
    if summary:
        parts.append(summary)
    parts.extend(str(line).strip() for line in context.source_context.attributes if str(line).strip())
    if context.selection_evidence.matched_topics:
        parts.append('topics: ' + ', '.join(context.selection_evidence.matched_topics[:6]))
    if context.selection_evidence.llm_reasons:
        parts.append('reasons: ' + '; '.join(context.selection_evidence.llm_reasons[:4]))
    return '\n'.join(part for part in parts if part).strip()


def _split_sentences(text: str) -> list[str]:
    normalized = str(text or '').replace('\r', '\n')
    chunks = []
    for block in normalized.split('\n'):
        block = block.strip()
        if not block:
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(block):
            cleaned = ' '.join(sentence.split()).strip()
            if cleaned:
                chunks.append(cleaned)
    return chunks


def _filter_noise(sentences: Iterable[str], anchor_text: str) -> list[str]:
    anchor_tokens = set(_tokenize(anchor_text))
    filtered: list[str] = []
    for sentence in sentences:
        text = str(sentence or '').strip()
        if len(text) < 12:
            continue
        lowered = text.lower()
        if any(pattern.lower() in lowered for pattern in _NOISE_PATTERNS):
            continue
        if lowered.count('|') >= 3:
            continue
        tokens = set(_tokenize(text))
        if len(tokens) < 2:
            continue
        if anchor_tokens and not tokens.intersection(anchor_tokens) and len(text) < 36:
            continue
        filtered.append(text)
    return filtered


def _dedupe_sentences(sentences: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for sentence in sentences:
        key = re.sub(r'\W+', '', sentence).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(sentence)
    return result


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(str(text or ''))]


def _lexical_rank(sentences: Sequence[str], anchor_text: str) -> list[RankedSentence]:
    anchor_tokens = Counter(_tokenize(anchor_text))
    sentence_tokens = [Counter(_tokenize(sentence)) for sentence in sentences]
    global_counts = Counter(token for counter in sentence_tokens for token in counter)
    ranked: list[RankedSentence] = []
    for index, sentence in enumerate(sentences):
        tokens = sentence_tokens[index]
        overlap = sum(min(count, anchor_tokens[token]) for token, count in tokens.items() if token in anchor_tokens)
        rarity = sum(1.0 / math.sqrt(global_counts[token]) for token in tokens)
        numeric_bonus = 1.0 if re.search(r'\d', sentence) else 0.0
        position_bonus = max(0.0, 1.0 - index * 0.03)
        density_bonus = min(2.0, len(tokens) / 12.0)
        score = overlap * 3.0 + rarity + numeric_bonus + position_bonus + density_bonus
        ranked.append(RankedSentence(index=index, text=sentence, score=score))
    ranked.sort(key=lambda row: (-row.score, row.index))
    return ranked


def _frequency_rank(sentences: Sequence[str]) -> list[RankedSentence]:
    frequencies = Counter(token for sentence in sentences for token in _tokenize(sentence))
    ranked: list[RankedSentence] = []
    for index, sentence in enumerate(sentences):
        score = sum(frequencies[token] for token in _tokenize(sentence)) + max(0.0, 1.0 - index * 0.03)
        ranked.append(RankedSentence(index=index, text=sentence, score=float(score)))
    ranked.sort(key=lambda row: (-row.score, row.index))
    return ranked


def _budget_pack(ranked: Sequence[RankedSentence], budget: int) -> tuple[str, ...]:
    packed: list[RankedSentence] = []
    total = 0
    for sentence in ranked:
        cost = len(sentence.text) + (1 if packed else 0)
        if packed and total + cost > budget:
            continue
        packed.append(sentence)
        total += cost
        if total >= budget:
            break
    packed.sort(key=lambda row: row.index)
    return tuple(row.text for row in packed)
