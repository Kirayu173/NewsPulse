# coding=utf-8
"""Batch quality-gate helpers for AI selection."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

from newspulse.workflow.selection.context_builder import build_selection_context
from newspulse.workflow.selection.models import AIBatchNewsItem, AIQualityDecision
from newspulse.workflow.shared.ai_runtime.errors import AIRuntimeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate
from newspulse.workflow.shared.contracts import HotlistItem
from newspulse.workflow.shared.options import SelectionOptions


class AIBatchClassifier:
    """Own AI batch preparation and keep/drop judgement."""

    def __init__(
        self,
        *,
        storage_manager: Any,
        client: Any,
        classify_prompt: PromptTemplate,
        request_overrides: Mapping[str, Any],
        sleep_func: Callable[[float], None],
    ):
        self.storage_manager = storage_manager
        self.client = client
        self.classify_prompt = classify_prompt
        self.request_overrides = dict(request_overrides)
        self.sleep_func = sleep_func

    def build_batch_items(self, snapshot_items: Iterable[HotlistItem]) -> list[AIBatchNewsItem]:
        """Build normalized AI batch items from snapshot items."""

        batch_items: list[AIBatchNewsItem] = []
        for prompt_id, item in enumerate(snapshot_items, start=1):
            context = build_selection_context(item)
            batch_items.append(
                AIBatchNewsItem(
                    prompt_id=prompt_id,
                    news_item_id=str(item.news_item_id),
                    title=item.title,
                    source_id=item.source_id,
                    source_name=item.source_name,
                    summary=context.summary,
                    context_lines=context.attributes,
                    rendered_context=context.llm_text,
                    persisted_news_id=_coerce_int(item.news_item_id, default=None),
                )
            )
        return batch_items

    def classify_pending_items(
        self,
        *,
        pending_items: Sequence[AIBatchNewsItem],
        interests_content: str,
        focus_topics: Sequence[str],
        options: SelectionOptions,
    ) -> list[AIQualityDecision]:
        """Classify pending items and return keep/drop decisions."""

        if not pending_items:
            return []

        all_results: list[AIQualityDecision] = []
        batch_size = max(1, int(options.ai.batch_size or 1))
        batch_interval = max(0.0, float(options.ai.batch_interval or 0.0))

        for batch_index, start in enumerate(range(0, len(pending_items), batch_size), start=1):
            if batch_index > 1 and batch_interval > 0:
                self.sleep_func(batch_interval)

            batch = list(pending_items[start : start + batch_size])
            batch_results = self.classify_batch(
                batch,
                interests_content=interests_content,
                focus_topics=focus_topics,
            )
            all_results.extend(batch_results)
        return all_results

    def classify_batch(
        self,
        batch_items: Sequence[AIBatchNewsItem],
        *,
        interests_content: str,
        focus_topics: Sequence[str] = (),
    ) -> list[AIQualityDecision]:
        """Judge one AI batch and recursively split on transient failures."""

        if not batch_items or self.classify_prompt.is_empty:
            return []

        try:
            decisions = self._classify_once(
                batch_items,
                interests_content=interests_content,
                focus_topics=focus_topics,
            )
        except AIRuntimeError:
            if len(batch_items) <= 1:
                raise
            return self._split_and_retry_batch(
                batch_items,
                interests_content=interests_content,
                focus_topics=focus_topics,
            )
        except Exception:
            if len(batch_items) <= 1:
                raise
            return self._split_and_retry_batch(
                batch_items,
                interests_content=interests_content,
                focus_topics=focus_topics,
            )

        if len(decisions) >= len(batch_items):
            return decisions

        missing_items = _missing_batch_items(batch_items, decisions)
        if not missing_items:
            return decisions
        if len(batch_items) <= 1:
            return decisions

        recovered = self._retry_missing_items(
            missing_items,
            interests_content=interests_content,
            focus_topics=focus_topics,
        )
        return _merge_batch_decisions(batch_items, decisions, recovered)

    def _classify_once(
        self,
        batch_items: Sequence[AIBatchNewsItem],
        *,
        interests_content: str,
        focus_topics: Sequence[str],
    ) -> list[AIQualityDecision]:
        user_prompt = _render_user_prompt(
            self.classify_prompt,
            {
                "interests_content": interests_content,
                "focus_topics": "\n".join(f"- {topic}" for topic in focus_topics if str(topic).strip()) or "-",
                "news_count": str(len(batch_items)),
                "news_list": _format_news_list(batch_items),
            },
        )
        response = self.client.generate_json(
            self.classify_prompt.build_messages(user_prompt),
            **self.request_overrides,
        )
        return self._parse_classify_response(response, batch_items)

    def _retry_missing_items(
        self,
        missing_items: Sequence[AIBatchNewsItem],
        *,
        interests_content: str,
        focus_topics: Sequence[str],
    ) -> list[AIQualityDecision]:
        if not missing_items:
            return []
        if len(missing_items) == 1:
            return self.classify_batch(
                missing_items,
                interests_content=interests_content,
                focus_topics=focus_topics,
            )
        return self._split_and_retry_batch(
            missing_items,
            interests_content=interests_content,
            focus_topics=focus_topics,
        )

    def _split_and_retry_batch(
        self,
        batch_items: Sequence[AIBatchNewsItem],
        *,
        interests_content: str,
        focus_topics: Sequence[str],
    ) -> list[AIQualityDecision]:
        if len(batch_items) <= 1:
            return []

        split_index = len(batch_items) // 2
        left = self.classify_batch(
            batch_items[:split_index],
            interests_content=interests_content,
            focus_topics=focus_topics,
        )
        right = self.classify_batch(
            batch_items[split_index:],
            interests_content=interests_content,
            focus_topics=focus_topics,
        )
        return _merge_batch_decisions(batch_items, left, right)

    def _parse_classify_response(
        self,
        response: Any,
        batch_items: Sequence[AIBatchNewsItem],
    ) -> list[AIQualityDecision]:
        payload = getattr(response, "json_payload", None)
        if not isinstance(payload, list):
            return []

        item_by_prompt_id = {item.prompt_id: item for item in batch_items}
        decisions: list[AIQualityDecision] = []
        seen_ids: set[str] = set()

        for entry in payload:
            if not isinstance(entry, Mapping):
                continue

            prompt_id = _coerce_int(entry.get("id"), default=None)
            if prompt_id is None or prompt_id not in item_by_prompt_id:
                continue
            news_item = item_by_prompt_id[prompt_id]
            if news_item.news_item_id in seen_ids:
                continue

            keep = bool(entry.get("keep", False))
            score = max(0.0, min(1.0, _coerce_float(entry.get("score", 0.0), default=0.0)))
            reasons = tuple(
                str(reason).strip()
                for reason in entry.get("reasons", [])
                if str(reason).strip()
            ) if isinstance(entry.get("reasons"), list) else ()
            matched_topics = tuple(
                str(topic).strip()
                for topic in entry.get("matched_topics", [])
                if str(topic).strip()
            ) if isinstance(entry.get("matched_topics"), list) else ()

            decisions.append(
                AIQualityDecision(
                    news_item_id=news_item.news_item_id,
                    keep=keep,
                    quality_score=score,
                    reasons=reasons,
                    evidence=str(entry.get("evidence", "") or "").strip(),
                    matched_topics=matched_topics,
                    persisted_news_id=news_item.persisted_news_id,
                    metadata={
                        "source_id": news_item.source_id,
                        "source_name": news_item.source_name,
                        "summary": news_item.summary,
                        "context_lines": list(news_item.context_lines),
                    },
                )
            )
            seen_ids.add(news_item.news_item_id)

        return decisions


def _format_news_list(batch_items: Sequence[AIBatchNewsItem]) -> str:
    rendered_items: list[str] = []
    for item in batch_items:
        lines = [f"{item.prompt_id}. [{item.source_name or item.source_id}] {item.title}"]
        rendered_context = str(item.rendered_context or "").strip()
        if rendered_context:
            lines.extend(
                f"   {line}"
                for line in rendered_context.splitlines()
                if str(line).strip()
            )
        rendered_items.append("\n".join(lines))
    return "\n".join(rendered_items)


def _render_user_prompt(template: PromptTemplate, replacements: Mapping[str, str]) -> str:
    user_prompt = template.user_prompt
    for key, value in replacements.items():
        user_prompt = user_prompt.replace("{" + key + "}", str(value))
    return user_prompt


def _missing_batch_items(
    batch_items: Sequence[AIBatchNewsItem],
    decisions: Sequence[AIQualityDecision],
) -> list[AIBatchNewsItem]:
    decided_ids = {decision.news_item_id for decision in decisions}
    return [item for item in batch_items if item.news_item_id not in decided_ids]


def _merge_batch_decisions(
    batch_items: Sequence[AIBatchNewsItem],
    *decision_sets: Sequence[AIQualityDecision],
) -> list[AIQualityDecision]:
    order = {item.news_item_id: index for index, item in enumerate(batch_items)}
    merged: dict[str, AIQualityDecision] = {}
    for decisions in decision_sets:
        for decision in decisions:
            merged.setdefault(decision.news_item_id, decision)
    return sorted(
        merged.values(),
        key=lambda decision: order.get(decision.news_item_id, len(order)),
    )


def _coerce_int(value: Any, default: int | None = 0) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
