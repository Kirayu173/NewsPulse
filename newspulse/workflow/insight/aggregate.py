# coding=utf-8
"""Aggregate theme summaries into stable global insight sections."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from newspulse.workflow.insight.models import (
    DEFAULT_SECTION_TEMPLATES,
    InsightNewsContext,
    InsightSectionTemplate,
    build_summary,
    resolve_section_title,
)
from newspulse.workflow.shared.ai_runtime.client import AIRuntimeClient
from newspulse.workflow.shared.ai_runtime.codec import extract_json_block
from newspulse.workflow.shared.ai_runtime.errors import AIResponseDecodeError
from newspulse.workflow.shared.ai_runtime.prompts import PromptTemplate, load_prompt_template
from newspulse.workflow.shared.ai_runtime.request_config import build_request_overrides
from newspulse.workflow.shared.contracts import InsightSection, InsightSummary, InsightSummaryBundle


class InsightAggregateGenerator:
    """Generate stable global insight sections from theme summaries."""

    def __init__(
        self,
        *,
        ai_runtime_config: Mapping[str, Any] | None = None,
        analysis_config: Mapping[str, Any] | None = None,
        config_root: str | Path | None = None,
        client: AIRuntimeClient | Any | None = None,
        prompt_template: PromptTemplate | None = None,
        section_templates: tuple[InsightSectionTemplate, ...] = DEFAULT_SECTION_TEMPLATES,
        request_overrides: Mapping[str, Any] | None = None,
    ):
        self.analysis_config = dict(analysis_config or {})
        self.config_root = Path(config_root) if config_root is not None else None
        self.section_templates = section_templates
        if client is None:
            if ai_runtime_config is None:
                raise ValueError("AI runtime config is required when no client is provided")
            client = AIRuntimeClient(ai_runtime_config)
        self.client = client
        self.prompt_template = prompt_template or load_prompt_template(
            self.analysis_config.get("PROMPT_FILE", "global_insight_prompt.txt"),
            config_root=self.config_root,
            required=True,
        )
        self.request_overrides = build_request_overrides(
            self.analysis_config,
            prompt_template=self.prompt_template,
            operation="insight",
            prompt_name="aggregate",
            overrides=request_overrides,
        )

    def generate(
        self,
        summaries: InsightSummaryBundle | Sequence[InsightSummary],
        contexts: Sequence[InsightNewsContext] = (),
    ) -> tuple[list[InsightSection], str, dict[str, Any]]:
        summary_bundle = _coerce_summary_bundle(summaries)
        valid_theme_summaries = [
            summary
            for summary in summary_bundle.theme_summaries
            if str(summary.key or "").strip() and str(summary.summary or "").strip()
        ]
        report_summary = summary_bundle.report_summary
        if not valid_theme_summaries and report_summary is None:
            return [], "", {"skipped": True, "reason": "no summaries available"}

        theme_payload = _build_theme_summary_payload(valid_theme_summaries)
        report_payload = asdict(report_summary) if report_summary is not None else {}
        source_distribution = _source_distribution(summary_bundle, contexts)
        topic_distribution = _topic_distribution(summary_bundle, contexts)
        user_prompt = self._render_prompt(theme_payload, report_payload, source_distribution, topic_distribution)
        raw_response = ""
        try:
            response = self.client.generate_json(
                self.prompt_template.build_messages(user_prompt),
                **self.request_overrides,
            )
            raw_response = response.text
            payload = response.json_payload
            sections = _coerce_sections(
                payload,
                summary_bundle=summary_bundle,
                section_templates=self.section_templates,
                source_distribution=source_distribution,
                topic_distribution=topic_distribution,
            )
            return sections, raw_response, {
                "summary_count": len(summary_bundle.summaries),
                "item_summary_count": len(summary_bundle.item_summaries),
                "theme_summary_count": len(valid_theme_summaries),
                "report_summary_present": report_summary is not None,
                "source_distribution": source_distribution,
                "topic_distribution": topic_distribution,
                "section_count": len(sections),
            }
        except Exception as exc:
            fallback = _fallback_section(summary_bundle, source_distribution, topic_distribution)
            return fallback, raw_response, {
                "summary_count": len(summary_bundle.summaries),
                "item_summary_count": len(summary_bundle.item_summaries),
                "theme_summary_count": len(valid_theme_summaries),
                "report_summary_present": report_summary is not None,
                "source_distribution": source_distribution,
                "topic_distribution": topic_distribution,
                "section_count": len(fallback),
                "error": f"{type(exc).__name__}: {exc}",
                "raw_preview": extract_json_block(raw_response)[:500],
            }

    def _render_prompt(
        self,
        theme_summary_payload: list[dict[str, Any]],
        report_summary_payload: dict[str, Any],
        source_distribution: dict[str, int],
        topic_distribution: dict[str, int],
    ) -> str:
        user_prompt = self.prompt_template.user_prompt
        replacements = {
            "summary_count": str(len(theme_summary_payload)),
            "theme_count": str(len(theme_summary_payload)),
            "theme_summaries_json": json.dumps(theme_summary_payload, ensure_ascii=False, indent=2),
            "report_summary_json": json.dumps(report_summary_payload, ensure_ascii=False, indent=2),
            "source_distribution_json": json.dumps(source_distribution, ensure_ascii=False, indent=2),
            "topic_distribution_json": json.dumps(topic_distribution, ensure_ascii=False, indent=2),
            "language": str(self.analysis_config.get("LANGUAGE", "Chinese") or "Chinese"),
        }
        for key, value in replacements.items():
            user_prompt = user_prompt.replace("{" + key + "}", str(value))
        return user_prompt


def _coerce_summary_bundle(summaries: InsightSummaryBundle | Sequence[InsightSummary]) -> InsightSummaryBundle:
    if isinstance(summaries, InsightSummaryBundle):
        return summaries
    item_summaries = [summary for summary in summaries if getattr(summary, "kind", "") == "item"]
    theme_summaries = [summary for summary in summaries if getattr(summary, "kind", "") == "theme"]
    report_summary = next((summary for summary in summaries if getattr(summary, "kind", "") == "report"), None)
    return InsightSummaryBundle(
        item_summaries=list(item_summaries),
        theme_summaries=list(theme_summaries),
        report_summary=report_summary,
    )


def _build_theme_summary_payload(theme_summaries: Sequence[InsightSummary]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for summary in theme_summaries:
        metadata = dict(summary.metadata or {})
        payload.append(
            {
                "key": summary.key,
                "title": summary.title,
                "summary": summary.summary,
                "item_ids": list(summary.item_ids),
                "theme_keys": list(summary.theme_keys),
                "evidence_topics": list(summary.evidence_topics),
                "evidence_notes": list(summary.evidence_notes),
                "representative_item_ids": list(metadata.get("representative_item_ids", [])),
                "supporting_item_ids": list(metadata.get("supporting_item_ids", [])),
                "representative_titles": list(metadata.get("representative_titles", [])),
                "source_evidence": list(summary.sources),
                "item_count": int(metadata.get("item_count", len(summary.item_ids)) or 0),
            }
        )
    return payload


def _source_distribution(summary_bundle: InsightSummaryBundle, contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for summary in summary_bundle.theme_summaries or summary_bundle.item_summaries:
        counter.update([source for source in summary.sources if source])
    if counter:
        return dict(counter)
    for context in contexts:
        counter.update([context.source_name or context.source_id or "unknown"])
    return dict(counter)


def _topic_distribution(summary_bundle: InsightSummaryBundle, contexts: Sequence[InsightNewsContext]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for summary in summary_bundle.theme_summaries or summary_bundle.item_summaries:
        counter.update(summary.evidence_topics)
    if counter:
        return dict(counter)
    for context in contexts:
        counter.update(context.selection_evidence.matched_topics)
    return dict(counter)


def _coerce_sections(
    payload: Any,
    *,
    summary_bundle: InsightSummaryBundle,
    section_templates: Sequence[InsightSectionTemplate],
    source_distribution: dict[str, int],
    topic_distribution: dict[str, int],
) -> list[InsightSection]:
    default_supporting_news_ids = _default_supporting_news_ids(summary_bundle)
    if isinstance(payload, Mapping) and isinstance(payload.get("sections"), list):
        sections: list[InsightSection] = []
        seen_keys: set[str] = set()
        for row in payload.get("sections", []):
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("key", "") or "").strip()
            content = str(row.get("content", "") or "").strip()
            if not key or not content or key in seen_keys:
                continue
            supporting_news_ids = _coerce_id_list(row.get("supporting_news_ids"))
            supporting_topics = _coerce_text_list(row.get("supporting_topics"))
            sections.append(
                InsightSection(
                    key=key,
                    title=resolve_section_title(key, fallback=str(row.get("title", key) or key)),
                    content=content,
                    summary=str(row.get("summary", "") or build_summary(content)).strip(),
                    metadata={
                        "supporting_news_ids": supporting_news_ids or default_supporting_news_ids,
                        "supporting_topics": supporting_topics or list(topic_distribution)[:6],
                        "source_distribution": _coerce_distribution(row.get("source_distribution")) or source_distribution,
                        "section_generator": "aggregate_llm",
                        "input_summary_keys": _input_summary_keys(summary_bundle),
                    },
                )
            )
            seen_keys.add(key)
        if sections:
            return sections

    if not isinstance(payload, Mapping):
        raise AIResponseDecodeError("aggregate insight payload must be a JSON object")

    sections: list[InsightSection] = []
    for template in section_templates:
        raw_value = payload.get(template.field_name)
        content = ""
        supporting_news_ids: list[str] = []
        supporting_topics: list[str] = []
        section_source_distribution: dict[str, int] = source_distribution
        if isinstance(raw_value, Mapping):
            content = str(raw_value.get("content", "") or "").strip()
            supporting_news_ids = _coerce_id_list(raw_value.get("supporting_news_ids"))
            supporting_topics = _coerce_text_list(raw_value.get("supporting_topics"))
            section_source_distribution = _coerce_distribution(raw_value.get("source_distribution")) or source_distribution
        else:
            content = str(raw_value or "").strip()
        if not content:
            continue
        sections.append(
            InsightSection(
                key=template.key,
                title=template.title,
                content=content,
                summary=build_summary(content, template.summary_limit),
                metadata={
                    "supporting_news_ids": supporting_news_ids or default_supporting_news_ids,
                    "supporting_topics": supporting_topics or list(topic_distribution)[:6],
                    "source_distribution": section_source_distribution,
                    "section_generator": "aggregate_llm",
                    "input_summary_keys": _input_summary_keys(summary_bundle),
                },
            )
        )
    if not sections:
        raise AIResponseDecodeError("aggregate insight payload did not contain any section content")
    return sections


def _fallback_section(
    summary_bundle: InsightSummaryBundle,
    source_distribution: Mapping[str, int],
    topic_distribution: Mapping[str, int],
) -> list[InsightSection]:
    report_summary = summary_bundle.report_summary
    theme_summaries = list(summary_bundle.theme_summaries)
    if report_summary is not None:
        content = report_summary.summary
    elif theme_summaries:
        content = "；".join(summary.summary for summary in theme_summaries[:3] if summary.summary)
    elif summary_bundle.item_summaries:
        content = "；".join(summary.summary for summary in summary_bundle.item_summaries[:3] if summary.summary)
    else:
        content = "No summary input was available for global insight generation."
    if theme_summaries:
        content = f"{content} 后续洞察基于主题摘要生成，重点主题包括：{', '.join(summary.title for summary in theme_summaries[:3])}。"
    return [
        InsightSection(
            key="core_trends",
            title=resolve_section_title("core_trends"),
            content=content.strip() or "No aggregate insight could be generated.",
            summary=build_summary(content),
            metadata={
                "supporting_news_ids": _default_supporting_news_ids(summary_bundle),
                "supporting_topics": list(topic_distribution)[:6],
                "source_distribution": dict(source_distribution),
                "section_generator": "aggregate_fallback",
                "input_summary_keys": _input_summary_keys(summary_bundle),
            },
        )
    ]


def _default_supporting_news_ids(summary_bundle: InsightSummaryBundle) -> list[str]:
    ids: list[str] = []
    for summary in summary_bundle.theme_summaries or summary_bundle.item_summaries:
        for item_id in summary.item_ids:
            text = str(item_id or "").strip()
            if text and text not in ids:
                ids.append(text)
            if len(ids) >= 8:
                return ids
    return ids


def _input_summary_keys(summary_bundle: InsightSummaryBundle) -> list[str]:
    return [summary.key for summary in summary_bundle.summaries if summary.key][:12]


def _coerce_id_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:8]


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:8]


def _coerce_distribution(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    payload: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            continue
        if count > 0:
            payload[name] = count
    return payload
