# coding=utf-8
"""LLM-backed item summary generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from newspulse.core.config_paths import DEFAULT_ITEM_SUMMARY_PROMPT_FILE
from newspulse.workflow.insight.content_models import ReducedSummaryContext
from newspulse.workflow.insight.content_preprocessor import to_prompt_payload
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response, extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides
from newspulse.workflow.shared.contracts import InsightSummary


class ItemSummaryGenerator:
    """Generate one item summary per reduced context through the AI runtime facade."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        summary_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        request_overrides: Mapping[str, Any] | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.summary_config = dict(summary_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.summary_config.get("ITEM_PROMPT_FILE", DEFAULT_ITEM_SUMMARY_PROMPT_FILE),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = build_request_overrides(
            self.analysis_config,
            prompt_template=self.prompt_template,
            operation="insight",
            prompt_name="item_summary",
            overrides=request_overrides,
        )

    def generate_many(
        self,
        contexts: Sequence[ReducedSummaryContext],
        *,
        max_workers: int = 1,
        batch_size: int = 3,
    ) -> tuple[list[InsightSummary], dict[str, Any]]:
        workers = max(1, int(max_workers or 1))
        effective_batch_size = max(1, int(batch_size or 1))
        batches = list(_chunk_contexts(contexts, effective_batch_size))
        index_by_id = {str(context.news_item_id): index for index, context in enumerate(contexts)}
        ordered: list[InsightSummary | None] = [None for _ in contexts]
        failures: list[dict[str, Any]] = []
        raw_responses: dict[str, str] = {}
        raw_responses_by_batch: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(self.generate_batch, batch): batch_index
                for batch_index, batch in enumerate(batches)
            }
            for future in as_completed(future_map):
                batch_index = future_map[future]
                batch = batches[batch_index]
                try:
                    summary_map, raw_response = future.result()
                    raw_responses_by_batch[str(batch_index)] = raw_response
                    for context in batch:
                        summary = summary_map.get(str(context.news_item_id))
                        if summary is None:
                            failures.append(
                                {
                                    "news_item_id": context.news_item_id,
                                    "title": context.title,
                                    "error_type": "AIResponseDecodeError",
                                    "message": "batch summary response did not contain this news_item_id",
                                }
                            )
                            continue
                        ordered[index_by_id[str(context.news_item_id)]] = summary
                        raw_responses[context.news_item_id] = raw_response
                except Exception as exc:
                    for context in batch:
                        failures.append(
                            {
                                "news_item_id": context.news_item_id,
                                "title": context.title,
                                "error_type": type(exc).__name__,
                                "message": str(exc),
                            }
                        )

        summaries = [summary for summary in ordered if summary is not None]
        return summaries, {
            "summary_model_calls": len(batches),
            "summary_concurrency": workers,
            "summary_batch_size": effective_batch_size,
            "summary_batch_count": len(batches),
            "item_summary_count": len(summaries),
            "item_summary_failed_count": len(failures),
            "failures": failures,
            "raw_response_by_item_id": raw_responses,
            "raw_response_by_batch": raw_responses_by_batch,
            "item_summary_payloads": [asdict(summary) for summary in summaries],
        }

    def generate_one(self, context: ReducedSummaryContext) -> tuple[InsightSummary, str]:
        summary_map, raw_response = self.generate_batch([context])
        summary = summary_map.get(str(context.news_item_id))
        if summary is None:
            raise AIResponseDecodeError("item summary response did not contain the requested news_item_id")
        return summary, raw_response

    def generate_batch(self, contexts: Sequence[ReducedSummaryContext]) -> tuple[dict[str, InsightSummary], str]:
        user_prompt = self._render_prompt(contexts)
        response = self.client.generate_json(
            self.prompt_template.build_messages(user_prompt),
            **self.request_overrides,
        )
        raw_response = str(getattr(response, "text", "") or "")
        payloads = _decode_batch_payload(response)
        payload_by_id = {str(payload.get("news_item_id") or "").strip(): payload for payload in payloads}
        summaries: dict[str, InsightSummary] = {}
        for context in contexts:
            item_id = str(context.news_item_id)
            payload = payload_by_id.get(item_id)
            if payload is None:
                continue
            summaries[item_id] = self._build_summary(context, payload)
        return summaries, raw_response

    def _build_summary(self, context: ReducedSummaryContext, payload: Mapping[str, Any]) -> InsightSummary:
        summary_text = _coerce_summary_text(payload)
        if not summary_text:
            raise AIResponseDecodeError("item summary response did not contain non-empty summary text")

        metadata = dict(context.metadata or {})
        quality_score = _coerce_float(payload.get("quality_score"), context.rank_signals.get("quality_score", 0.0))
        metadata.update(
            {
                "summary_scope": "item",
                "news_item_id": context.news_item_id,
                "source_id": str(metadata.get("source_id", "") or ""),
                "quality_score": quality_score,
                "current_rank": int(context.rank_signals.get("current_rank", 0) or 0),
                "generation_status": "ok",
                "reduced_context_chars": context.reduced_char_count,
            }
        )
        evidence_notes = _compact_values(
            _coerce_text_list(payload.get("evidence_notes")) or context.evidence_notes,
            limit=8,
        )
        return InsightSummary(
            kind="item",
            key=f"item:{context.news_item_id}",
            title=str(payload.get("title") or context.title or "").strip(),
            summary=summary_text,
            item_ids=[context.news_item_id],
            evidence_topics=_compact_values(context.evidence_topics, limit=8),
            evidence_notes=evidence_notes,
            sources=[context.source] if context.source else [],
            expanded=True,
            metadata=metadata,
        )

    def _render_prompt(self, contexts: Sequence[ReducedSummaryContext]) -> str:
        replacements = {
            "item_contexts_json": json.dumps(
                [to_prompt_payload(context) for context in contexts],
                ensure_ascii=False,
                indent=2,
            ),
            "max_summary_chars": str(int(self.summary_config.get("ITEM_SUMMARY_MAX_CHARS", 220) or 220)),
            "language": str(self.analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }
        user_prompt = self.prompt_template.user_prompt
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", value)
        return user_prompt


def _decode_batch_payload(response: Any) -> list[dict[str, Any]]:
    payload = decode_json_response(response)
    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError(
            "batch item summary response must be a JSON object",
            details={"raw_preview": extract_json_block(response)[:200]},
        )
    items = payload.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise AIResponseDecodeError(
            "batch item summary response must contain an items array",
            details={"raw_preview": extract_json_block(response)[:200]},
        )
    normalized = [dict(item) for item in items if isinstance(item, Mapping)]
    if len(normalized) != len(items):
        raise AIResponseDecodeError(
            "batch item summary items must be JSON objects",
            details={"raw_preview": extract_json_block(response)[:200]},
        )
    return normalized


def _chunk_contexts(contexts: Sequence[ReducedSummaryContext], batch_size: int) -> list[Sequence[ReducedSummaryContext]]:
    return [contexts[start : start + batch_size] for start in range(0, len(contexts), batch_size)]


def _coerce_summary_text(payload: Mapping[str, Any]) -> str:
    for key in ("summary", "item_summary", "text"):
        text = " ".join(str(payload.get(key, "") or "").split())
        if text:
            return text
    return ""


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _compact_values(values: Sequence[str] | tuple[str, ...], *, limit: int) -> list[str]:
    normalized: list[str] = []
    for raw in values or ():
        text = " ".join(str(raw or "").split())
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _coerce_float(value: Any, default: Any = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return 0.0
