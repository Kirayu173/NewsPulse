# coding=utf-8
"""LLM-backed report summary generation from item summaries only."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import decode_json_response, extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides
from newspulse.workflow.shared.contracts import InsightSummary


class ReportSummaryGenerator:
    """Create the report-level summary using successful item summaries."""

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
            self.summary_config.get("REPORT_PROMPT_FILE", "insight/report_summary_prompt.txt"),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = build_request_overrides(
            self.analysis_config,
            prompt_template=self.prompt_template,
            operation="insight",
            prompt_name="report_summary",
            overrides=request_overrides,
        )

    def generate(
        self,
        item_summaries: Sequence[InsightSummary],
        *,
        failed_item_summary_count: int = 0,
    ) -> tuple[InsightSummary | None, str, dict[str, Any]]:
        valid_items = [
            summary
            for summary in item_summaries
            if summary.kind == "item" and str(summary.summary or "").strip()
        ]
        if not valid_items:
            return None, "", {
                "skipped": True,
                "reason": "no item summaries available",
                "item_summary_count": 0,
                "failed_item_summary_count": int(failed_item_summary_count or 0),
            }

        user_prompt = self._render_prompt(valid_items)
        response = self.client.generate_json(
            self.prompt_template.build_messages(user_prompt),
            **self.request_overrides,
        )
        raw_response = str(getattr(response, "text", "") or "")
        payload = _decode_payload(response)
        summary_text = _coerce_summary_text(payload)
        if not summary_text:
            raise AIResponseDecodeError("report summary response did not contain non-empty summary text")

        topic_counts = _topic_distribution(valid_items)
        source_counts = _source_distribution(valid_items)
        item_ids = _item_ids(valid_items)
        summary = InsightSummary(
            kind="report",
            key="report",
            title=str(payload.get("title") or "报告摘要").strip(),
            summary=summary_text,
            item_ids=item_ids,
            evidence_topics=list(topic_counts)[:10],
            evidence_notes=_compact_values(_coerce_text_list(payload.get("evidence_notes")), limit=8),
            sources=list(source_counts)[:8],
            expanded=True,
            metadata={
                "summary_scope": "report",
                "generation_status": "ok",
                "item_summary_count": len(valid_items),
                "failed_item_summary_count": int(failed_item_summary_count or 0),
                "source_distribution": dict(source_counts),
                "topic_distribution": dict(topic_counts),
            },
        )
        return summary, raw_response, {
            "item_summary_count": len(valid_items),
            "failed_item_summary_count": int(failed_item_summary_count or 0),
            "report_summary_present": True,
            "report_summary_payload": asdict(summary),
        }

    def _render_prompt(self, item_summaries: Sequence[InsightSummary]) -> str:
        payload = _build_item_payloads(item_summaries)
        replacements = {
            "item_summary_count": str(len(item_summaries)),
            "item_summaries_json": json.dumps(payload, ensure_ascii=False, indent=2),
            "source_distribution_json": json.dumps(_source_distribution(item_summaries), ensure_ascii=False, indent=2),
            "topic_distribution_json": json.dumps(_topic_distribution(item_summaries), ensure_ascii=False, indent=2),
            "max_summary_chars": str(int(self.summary_config.get("REPORT_SUMMARY_MAX_CHARS", 300) or 300)),
            "language": str(self.analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }
        user_prompt = self.prompt_template.user_prompt
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", value)
        return user_prompt


def _build_item_payloads(item_summaries: Sequence[InsightSummary]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for summary in item_summaries:
        metadata = dict(summary.metadata or {})
        payload.append(
            {
                "key": summary.key,
                "title": summary.title,
                "summary": summary.summary,
                "item_ids": list(summary.item_ids),
                "topics": list(summary.evidence_topics),
                "source": summary.sources[0] if summary.sources else "",
                "quality_score": float(metadata.get("quality_score", 0.0) or 0.0),
                "current_rank": int(metadata.get("current_rank", 0) or 0),
            }
        )
    return payload


def _decode_payload(response: Any) -> dict[str, Any]:
    payload = decode_json_response(response)
    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError(
            "report summary response must be a JSON object",
            details={"raw_preview": extract_json_block(response)[:200]},
        )
    return dict(payload)


def _coerce_summary_text(payload: Mapping[str, Any]) -> str:
    for key in ("summary", "report_summary", "text"):
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


def _source_distribution(item_summaries: Sequence[InsightSummary]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for summary in item_summaries:
        counter.update(source for source in summary.sources if source)
    return dict(counter)


def _topic_distribution(item_summaries: Sequence[InsightSummary]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for summary in item_summaries:
        counter.update(topic for topic in summary.evidence_topics if topic)
    return dict(counter)


def _item_ids(item_summaries: Sequence[InsightSummary]) -> list[str]:
    rows: list[str] = []
    for summary in item_summaries:
        for item_id in summary.item_ids:
            text = str(item_id or "").strip()
            if text and text not in rows:
                rows.append(text)
    return rows
