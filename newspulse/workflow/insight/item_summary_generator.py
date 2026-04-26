# coding=utf-8
"""LLM-backed item summary generation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
            self.summary_config.get("ITEM_PROMPT_FILE", "insight/item_summary_prompt.txt"),
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
    ) -> tuple[list[InsightSummary], dict[str, Any]]:
        workers = max(1, int(max_workers or 1))
        ordered: list[InsightSummary | None] = [None for _ in contexts]
        failures: list[dict[str, Any]] = []
        raw_responses: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(self.generate_one, context): index
                for index, context in enumerate(contexts)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                context = contexts[index]
                try:
                    summary, raw_response = future.result()
                    ordered[index] = summary
                    raw_responses[context.news_item_id] = raw_response
                except Exception as exc:
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
            "summary_model_calls": len(contexts),
            "summary_concurrency": workers,
            "item_summary_count": len(summaries),
            "item_summary_failed_count": len(failures),
            "failures": failures,
            "raw_response_by_item_id": raw_responses,
            "item_summary_payloads": [asdict(summary) for summary in summaries],
        }

    def generate_one(self, context: ReducedSummaryContext) -> tuple[InsightSummary, str]:
        user_prompt = self._render_prompt(context)
        response = self.client.generate_json(
            self.prompt_template.build_messages(user_prompt),
            **self.request_overrides,
        )
        raw_response = str(getattr(response, "text", "") or "")
        payload = _decode_payload(response)
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
        return (
            InsightSummary(
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
            ),
            raw_response,
        )

    def _render_prompt(self, context: ReducedSummaryContext) -> str:
        replacements = {
            "item_context_json": json.dumps(to_prompt_payload(context), ensure_ascii=False, indent=2),
            "max_summary_chars": str(int(self.summary_config.get("ITEM_SUMMARY_MAX_CHARS", 220) or 220)),
            "language": str(self.analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }
        user_prompt = self.prompt_template.user_prompt
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", value)
        return user_prompt


def _decode_payload(response: Any) -> dict[str, Any]:
    payload = decode_json_response(response)
    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError(
            "item summary response must be a JSON object",
            details={"raw_preview": extract_json_block(response)[:200]},
        )
    return dict(payload)


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
