# coding=utf-8
"""Semantic relevance filter for the selection funnel."""

from __future__ import annotations

import math
from typing import Any, Iterable, Protocol, Sequence

from newspulse.workflow.selection.context_builder import build_selection_context
from newspulse.workflow.selection.models import (
    SelectionCandidate,
    SelectionTopic,
    SemanticSelectionResult,
)
from newspulse.workflow.shared.contracts import HotlistItem, SelectionRejectedItem
from newspulse.workflow.shared.options import SelectionSemanticOptions


class SelectionReranker(Protocol):
    """Optional reranker hook used after the first semantic recall pass."""

    def rerank(
        self,
        item: HotlistItem,
        candidates: Sequence[SelectionCandidate],
    ) -> list[SelectionCandidate]:
        """Return the reranked candidate list for a single item."""


class NoopSelectionReranker:
    """Default reranker that keeps the original semantic ordering."""

    def rerank(
        self,
        item: HotlistItem,
        candidates: Sequence[SelectionCandidate],
    ) -> list[SelectionCandidate]:
        return list(candidates)


class SemanticSelectionLayer:
    """Run embedding-based relevance filtering ahead of the LLM gate."""

    def __init__(
        self,
        *,
        embedding_client: Any | None = None,
        reranker: SelectionReranker | None = None,
    ):
        self.embedding_client = embedding_client
        self.reranker = reranker or NoopSelectionReranker()

    def is_enabled(self) -> bool:
        """Return True when an embedding client is available."""

        return self.embedding_client is not None and (
            not hasattr(self.embedding_client, "is_enabled") or bool(self.embedding_client.is_enabled())
        )

    def select(
        self,
        snapshot_items: Sequence[HotlistItem],
        topics: Sequence[SelectionTopic],
        options: SelectionSemanticOptions,
    ) -> SemanticSelectionResult:
        """Score items against focus topics and reject weakly related items."""

        if not options.enabled:
            return SemanticSelectionResult(
                topics=tuple(topics),
                passed_items=tuple(snapshot_items),
                diagnostics={"enabled": False, "skipped": True, "reason": "disabled"},
            )
        if not snapshot_items:
            return SemanticSelectionResult(
                topics=tuple(topics),
                diagnostics={"enabled": True, "skipped": True, "reason": "no_items"},
            )
        if not topics:
            return SemanticSelectionResult(
                passed_items=tuple(snapshot_items),
                diagnostics={"enabled": True, "skipped": True, "reason": "no_topics"},
            )
        if not self.is_enabled():
            return SemanticSelectionResult(
                topics=tuple(topics),
                passed_items=tuple(snapshot_items),
                diagnostics={"enabled": True, "skipped": True, "reason": "embedding_unavailable"},
            )

        item_contexts = [build_selection_context(item) for item in snapshot_items]
        item_texts = [context.embedding_text for context in item_contexts]
        topic_texts = [topic.to_query_text() for topic in topics]
        try:
            item_vectors = _coerce_vectors(self.embedding_client.embed_texts(item_texts))
            topic_vectors = _coerce_vectors(self.embedding_client.embed_texts(topic_texts))
        except Exception as exc:
            return SemanticSelectionResult(
                topics=tuple(topics),
                passed_items=tuple(snapshot_items),
                diagnostics={
                    "enabled": True,
                    "skipped": True,
                    "reason": f"embedding_error:{type(exc).__name__}",
                },
            )

        top_k = max(1, int(options.top_k or 1))
        min_score = float(options.min_score or 0.0)

        candidates: list[SelectionCandidate] = []
        passed_items: list[HotlistItem] = []
        rejected_items: list[SelectionRejectedItem] = []
        topic_lookup = {topic.topic_id: topic for topic in topics}

        for item, item_context, item_text, item_vector in zip(
            snapshot_items,
            item_contexts,
            item_texts,
            item_vectors,
            strict=True,
        ):
            scored_candidates: list[SelectionCandidate] = []
            for topic, topic_text, topic_vector in zip(topics, topic_texts, topic_vectors, strict=True):
                score = _cosine_similarity(item_vector, topic_vector)
                if score < min_score:
                    continue
                scored_candidates.append(
                    SelectionCandidate(
                        news_item=item,
                        topic_id=topic.topic_id,
                        topic_label=topic.label,
                        score=score,
                        source_layers=("semantic",),
                        evidence={
                            "item_text": item_text,
                            "item_summary": item_context.summary,
                            "context_attributes": list(item_context.attributes),
                            "topic_text": topic_text,
                            "topic_priority": topic.priority,
                            "topic_source": topic.source,
                        },
                    )
                )

            scored_candidates.sort(
                key=lambda candidate: (
                    -candidate.score,
                    topic_lookup[candidate.topic_id].priority,
                    candidate.topic_label.lower(),
                )
            )
            reranked = self.reranker.rerank(item, scored_candidates[:top_k])
            candidates.extend(reranked)

            if reranked:
                passed_items.append(item)
                continue

            rejected_items.append(
                SelectionRejectedItem(
                    news_item_id=str(item.news_item_id),
                    source_id=item.source_id,
                    source_name=item.source_name,
                    title=item.title,
                    rejected_stage="semantic",
                    rejected_reason=f"semantic score below threshold {min_score:.2f}",
                    score=0.0,
                    metadata={"min_score": min_score},
                )
            )

        diagnostics = {
            "enabled": True,
            "skipped": False,
            "topic_count": len(topics),
            "candidate_count": len(candidates),
            "passed_count": len(passed_items),
            "rejected_count": len(rejected_items),
            "top_k": top_k,
            "min_score": min_score,
        }
        model_name = getattr(getattr(self.embedding_client, "config", None), "model", "")
        if model_name:
            diagnostics["model"] = model_name

        return SemanticSelectionResult(
            topics=tuple(topics),
            candidates=tuple(candidates),
            decisions=(),
            passed_items=tuple(passed_items),
            rejected_items=tuple(rejected_items),
            diagnostics=diagnostics,
        )


def _cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_list = [float(value) for value in left]
    right_list = [float(value) for value in right]
    if not left_list or not right_list or len(left_list) != len(right_list):
        return 0.0

    numerator = sum(a * b for a, b in zip(left_list, right_list, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left_list))
    right_norm = math.sqrt(sum(b * b for b in right_list))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _coerce_vectors(value: Any) -> list[list[float]]:
    vectors = getattr(value, "vectors", value)
    return [[float(component) for component in row] for row in vectors]
